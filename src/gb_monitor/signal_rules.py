from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from gb_monitor.models import SignalCandidate, SignalMatch, SignalRejection, SignalRule

AMBIGUOUS_MARGIN = 2


def load_signal_rules(path: Path) -> list[SignalRule]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stores = payload.get("stores")
    if not isinstance(stores, list):
        raise ValueError("signal rules stores must be list")

    rules: list[SignalRule] = []
    for idx, item in enumerate(stores):
        if not isinstance(item, dict):
            raise ValueError(f"stores[{idx}] must be object")

        store_id = str(item.get("store_id", "")).strip()
        store_name = str(item.get("store_name", "")).strip()
        platform = str(item.get("platform", "")).strip().lower()
        include_keywords = _ensure_str_list(item.get("include_keywords"))
        exact_include_keywords = _ensure_str_list(item.get("exact_include_keywords"))
        exclude_keywords = _ensure_str_list(item.get("exclude_keywords"))
        required_all_keywords = _ensure_str_list(item.get("required_all_keywords"))
        required_context_keywords = _ensure_str_list(item.get("required_context_keywords"))
        required_location_keywords = _ensure_str_list(item.get("required_location_keywords"))
        required_any_fields = _ensure_str_list(item.get("required_any_fields")) or [
            "title",
            "content",
            "poi_name",
        ]
        author_include_keywords = _ensure_str_list(item.get("author_include_keywords"))
        author_exclude_keywords = _ensure_str_list(item.get("author_exclude_keywords"))
        author_level_include_keywords = _ensure_str_list(item.get("author_level_include_keywords"))
        focus_author_names = _ensure_str_list(item.get("focus_author_names"))
        focus_author_tags = _ensure_str_list(item.get("focus_author_tags"))
        focus_verified_labels = _ensure_str_list(item.get("focus_verified_labels"))
        min_follower_count = _normalize_non_negative_int(item.get("min_follower_count"))
        require_poi = bool(item.get("require_poi", False))
        min_score = int(item.get("min_score", 5))

        if not store_id or not store_name or not platform:
            raise ValueError(f"stores[{idx}] missing store_id/store_name/platform")

        rules.append(
            SignalRule(
                store_id=store_id,
                store_name=store_name,
                platform=platform,
                include_keywords=include_keywords,
                exact_include_keywords=exact_include_keywords,
                exclude_keywords=exclude_keywords,
                required_all_keywords=required_all_keywords,
                required_context_keywords=required_context_keywords,
                required_location_keywords=required_location_keywords,
                required_any_fields=required_any_fields,
                author_include_keywords=author_include_keywords,
                author_exclude_keywords=author_exclude_keywords,
                author_level_include_keywords=author_level_include_keywords,
                focus_author_names=focus_author_names,
                focus_author_tags=focus_author_tags,
                focus_verified_labels=focus_verified_labels,
                min_follower_count=min_follower_count,
                require_poi=require_poi,
                min_score=min_score,
            )
        )

    return rules


def load_signal_candidates(path: Path) -> list[SignalCandidate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("signal input items must be list")

    default_platform = str(payload.get("platform", "")).strip().lower()
    candidates: list[SignalCandidate] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"items[{idx}] must be object")

        platform = str(item.get("platform") or default_platform).strip().lower()
        if not platform:
            raise ValueError(f"items[{idx}] missing platform")

        content_id = str(item.get("content_id") or item.get("url") or f"item-{idx}").strip()
        candidates.append(
            SignalCandidate(
                content_id=content_id,
                platform=platform,
                title=str(item.get("title", "")).strip(),
                content=str(item.get("content", "")).strip(),
                poi_name=str(item.get("poi_name", "")).strip(),
                author_name=str(item.get("author_name", "")).strip(),
                author_level=str(item.get("author_level", "")).strip(),
                verified_label=str(item.get("verified_label", "")).strip(),
                follower_count=_normalize_non_negative_int(item.get("follower_count")),
                author_tags=_normalize_tag_list(item.get("author_tags") or item.get("account_tags")),
                ip_location=str(item.get("ip_location", "")).strip(),
                topic_tags=_normalize_tag_list(item.get("topic_tags") or item.get("hashtags")),
                url=str(item.get("url", "")).strip(),
                published_at=_normalize_optional_text(item.get("published_at")),
                like_count=_normalize_non_negative_int(item.get("like_count")),
                favorite_count=_normalize_non_negative_int(
                    item.get("favorite_count") or item.get("collect_count")
                ),
                comment_count=_normalize_non_negative_int(item.get("comment_count")),
                share_count=_normalize_non_negative_int(item.get("share_count")),
                raw_payload=item,
            )
        )
    return candidates


def match_candidates(
    rules: list[SignalRule],
    candidates: list[SignalCandidate],
    min_score_override: int | None = None,
    allow_ambiguous: bool = False,
) -> list[SignalMatch]:
    matches, _ = review_candidates(
        rules=rules,
        candidates=candidates,
        min_score_override=min_score_override,
        allow_ambiguous=allow_ambiguous,
    )
    return matches


def review_candidates(
    rules: list[SignalRule],
    candidates: list[SignalCandidate],
    min_score_override: int | None = None,
    allow_ambiguous: bool = False,
) -> tuple[list[SignalMatch], list[SignalRejection]]:
    matches_by_key: dict[tuple[str, str], SignalMatch] = {}
    candidate_rejections: dict[str, SignalRejection] = {}
    for candidate in candidates:
        platform_rules = [rule for rule in rules if candidate.platform == rule.platform]
        if not platform_rules:
            continue

        for rule in rules:
            if candidate.platform != rule.platform:
                continue
            match, rejection_reason = _evaluate_single(rule, candidate, min_score_override)
            if match is None:
                if rejection_reason and candidate.content_id not in candidate_rejections:
                    candidate_rejections[candidate.content_id] = _build_rejection(rule, candidate, rejection_reason)
                continue
            key = (rule.store_id, candidate.content_id)
            previous = matches_by_key.get(key)
            if previous is None or match.score > previous.score:
                matches_by_key[key] = match

    matches, ambiguous_rejections = _collapse_ambiguous_matches(
        list(matches_by_key.values()),
        candidates=candidates,
        allow_ambiguous=allow_ambiguous,
    )
    matches.sort(key=lambda item: (-item.score, item.store_id, item.content_id))
    for rejection in ambiguous_rejections:
        candidate_rejections[rejection.content_id] = rejection
    accepted_ids = {item.content_id for item in matches}
    rejections = [
        item
        for content_id, item in candidate_rejections.items()
        if content_id not in accepted_ids
    ]
    rejections.sort(
        key=lambda item: (
            -(item.like_count + item.comment_count * 2 + item.share_count * 3),
            item.store_id,
            item.content_id,
        )
    )
    return matches, rejections


def build_signal_report(now: datetime, matches: list[SignalMatch]) -> str:
    lines = [f"[{now:%Y-%m-%d %H:%M:%S}] 门店实时舆情精筛结果"]
    if not matches:
        lines.append("未命中高置信内容")
        return "\n".join(lines)

    lines.append(f"命中条数: {len(matches)}")
    for item in matches:
        title = item.title or item.url or item.content_id
        lines.append(
            f"- {item.store_name} / {item.platform} / {item.confidence} / 分数{item.score}: {title}"
        )
        lines.append(f"  命中字段: {', '.join(item.matched_fields)}")
        lines.append(f"  命中词: {', '.join(item.matched_terms)}")
        if item.author_name:
            lines.append(f"  作者: {item.author_name}")
        if item.author_level:
            lines.append(f"  发布者级别: {item.author_level}")
        if item.verified_label:
            lines.append(f"  认证信息: {item.verified_label}")
        if item.follower_count > 0:
            lines.append(f"  粉丝量: {item.follower_count}")
        if item.author_tags:
            lines.append(f"  账号标签: {', '.join(item.author_tags)}")
        lines.append(f"  KOL判定: {_kol_tier(item)}")
        if item.focus_author_hits:
            lines.append(f"  重点达人命中: {', '.join(item.focus_author_hits)}")
        if item.ip_location:
            lines.append(f"  IP地域: {item.ip_location}")
        if item.poi_name:
            lines.append(f"  绑定门店: {item.poi_name}")
        if item.topic_tags:
            lines.append(f"  话题标签: {', '.join(item.topic_tags)}")
        if item.published_at:
            lines.append(f"  发布时间: {item.published_at}")
        if _engagement_score(item) > 0:
            lines.append(f"  互动: {_engagement_summary(item)}")
        if item.attribution_summary:
            lines.append(f"  引流观察: {item.attribution_summary}")
        if item.url:
            lines.append(f"  链接: {item.url}")
        lines.append(f"  说明: {item.reason}")
    return "\n".join(lines)


def build_signal_dashboard(
    now: datetime,
    matches: list[SignalMatch],
    rejections: list[SignalRejection] | None = None,
) -> str:
    lines = [f"# 门店实时舆情看板", "", f"- 生成时间：{now:%Y-%m-%d %H:%M:%S}"]
    rejections = rejections or []
    if not matches:
        lines.extend(
            [
                "- 命中结果：0",
                f"- 已过滤噪音：{len(rejections)}",
                "",
                "当前没有高置信内容。",
            ]
        )
        if rejections:
            lines.extend(_build_rejection_section(rejections))
        return "\n".join(lines)

    confidence_counts: dict[str, int] = {}
    platform_counts: dict[str, int] = {}
    for item in matches:
        confidence_counts[item.confidence] = confidence_counts.get(item.confidence, 0) + 1
        platform_counts[item.platform] = platform_counts.get(item.platform, 0) + 1

    lines.extend(
        [
            f"- 命中总数：{len(matches)}",
            f"- 高置信：{confidence_counts.get('高置信', 0)}",
            f"- 中高置信：{confidence_counts.get('中高置信', 0)}",
            f"- 基础命中：{confidence_counts.get('基础命中', 0)}",
            f"- 已过滤噪音：{len(rejections)}",
            "",
            "## 平台分布",
            "",
            "| 平台 | 命中数 |",
            "| --- | ---: |",
        ]
    )
    for platform, count in sorted(platform_counts.items()):
        lines.append(f"| {platform} | {count} |")

    lines.extend(
        [
            "",
            "## 命中明细",
            "",
            "| 平台 | 置信 | 分数 | 标题 | 作者/IP | 时间 | 互动 | 规则说明 |",
            "| --- | --- | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for item in matches:
        heat = _engagement_summary(item)
        title = _markdown_cell(item.title or item.url or item.content_id)
        author_bits = [item.author_name or "-"]
        if item.author_level:
            author_bits.append(item.author_level)
        if item.verified_label:
            author_bits.append(item.verified_label)
        if item.follower_count > 0:
            author_bits.append(f"粉丝{item.follower_count}")
        kol_tier = _kol_tier(item)
        if kol_tier != "普通账号":
            author_bits.append(kol_tier)
        if item.focus_author_hits:
            author_bits.append("重点达人命中")
        if item.ip_location:
            author_bits.append(item.ip_location)
        author = _markdown_cell(" / ".join(author_bits))
        published_at = _markdown_cell(item.published_at or "-")
        reason = _markdown_cell(item.reason)
        lines.append(
            f"| {item.platform} | {item.confidence} | {item.score} | {title} | {author} | {published_at} | {heat} | {reason} |"
        )
        if item.author_tags:
            lines.append(
                f"| 达人标签 | - | - | {_markdown_cell(', '.join(item.author_tags))} | - | - | - | - |"
            )
        if item.focus_author_hits:
            lines.append(
                f"| 重点名单 | - | - | {_markdown_cell(', '.join(item.focus_author_hits))} | - | - | - | - |"
            )
        if item.attribution_summary:
            lines.append(f"| 经营观察 | - | - | {_markdown_cell(item.attribution_summary)} | - | - | - | - |")

    if rejections:
        lines.extend(_build_rejection_section(rejections))

    return "\n".join(lines)


def matches_to_json(matches: list[SignalMatch]) -> list[dict[str, object]]:
    return [asdict(item) for item in matches]


def _evaluate_single(
    rule: SignalRule,
    candidate: SignalCandidate,
    min_score_override: int | None,
) -> tuple[SignalMatch | None, str | None]:
    field_values = {
        "title": candidate.title,
        "content": candidate.content,
        "poi_name": candidate.poi_name,
        "author_name": candidate.author_name,
        "author_level": candidate.author_level,
        "verified_label": candidate.verified_label,
        "author_tags": " ".join(candidate.author_tags),
        "topic_tags": " ".join(candidate.topic_tags),
        "ip_location": candidate.ip_location,
    }

    exclude_hits = _find_hits(rule.exclude_keywords, field_values)
    if exclude_hits:
        terms = sorted({term for values in exclude_hits.values() for term in values})
        return None, f"命中排除词：{', '.join(terms)}"

    if rule.author_exclude_keywords:
        author_exclude_hits = _find_hits(rule.author_exclude_keywords, {"author_name": candidate.author_name})
        if author_exclude_hits:
            terms = sorted({term for values in author_exclude_hits.values() for term in values})
            return None, f"作者命中黑名单：{', '.join(terms)}"

    author_include_hits = _find_hits(rule.author_include_keywords, {"author_name": candidate.author_name})
    if rule.author_include_keywords and not author_include_hits:
        return None, "作者未命中白名单"

    author_level_hits = _find_hits(
        rule.author_level_include_keywords,
        {"author_level": candidate.author_level, "verified_label": candidate.verified_label},
    )
    if rule.author_level_include_keywords and not author_level_hits:
        return None, "作者级别未命中白名单"

    focus_author_name_hits = _find_hits(rule.focus_author_names, {"author_name": candidate.author_name})
    focus_author_tag_hits = _find_hits(
        rule.focus_author_tags,
        {
            "author_tags": " ".join(candidate.author_tags),
            "author_level": candidate.author_level,
            "verified_label": candidate.verified_label,
        },
    )
    focus_verified_hits = _find_hits(
        rule.focus_verified_labels,
        {"verified_label": candidate.verified_label},
    )
    focus_author_hits = _merge_hits(focus_author_name_hits, focus_author_tag_hits, focus_verified_hits)

    if rule.min_follower_count > 0 and candidate.follower_count < rule.min_follower_count:
        return None, f"粉丝量不足：{candidate.follower_count} < {rule.min_follower_count}"

    if rule.require_poi and not candidate.poi_name:
        return None, "缺少POI门店锚点"

    exact_hits = _find_hits(rule.exact_include_keywords, field_values)
    core_terms = [rule.store_name, *rule.include_keywords]
    required_hits = _find_hits(core_terms, {k: v for k, v in field_values.items() if k in rule.required_any_fields})
    if not required_hits and not exact_hits:
        return None, "未命中门店核心词"

    if rule.required_all_keywords:
        required_all_hits = _find_hits(rule.required_all_keywords, field_values)
        required_all_terms = {term for values in required_all_hits.values() for term in values}
        missing_terms = [term for term in rule.required_all_keywords if term not in required_all_terms]
        if missing_terms:
            return None, f"缺少必备词：{', '.join(missing_terms)}"

    total_hits = _find_hits(core_terms, field_values)
    if not total_hits and not exact_hits:
        return None, "未命中门店规则词"

    has_strong_store_hit = bool(
        exact_hits.get("poi_name")
        or exact_hits.get("title")
        or _find_hits([rule.store_name], {"poi_name": candidate.poi_name, "title": candidate.title})
    )

    context_hits = _find_hits(rule.required_context_keywords, field_values)
    if rule.required_context_keywords and not has_strong_store_hit and not context_hits:
        return None, "缺少餐饮/探店上下文"

    location_hits = _find_hits(rule.required_location_keywords, field_values)
    if rule.required_location_keywords and not has_strong_store_hit and not location_hits:
        return None, "缺少门店位置上下文"

    combined_hits = _merge_hits(
        total_hits,
        exact_hits,
        context_hits,
        location_hits,
        author_level_hits,
        focus_author_hits,
    )
    matched_terms = sorted({term for hits in combined_hits.values() for term in hits})
    matched_terms.extend(
        sorted({term for hits in author_include_hits.values() for term in hits if term not in matched_terms})
    )
    matched_fields = sorted(combined_hits)
    if author_include_hits and "author_name" not in matched_fields:
        matched_fields.append("author_name")
    score = _score_match(
        rule,
        candidate,
        total_hits,
        exact_hits,
        context_hits,
        location_hits,
        author_include_hits,
        author_level_hits,
        focus_author_hits,
    )
    min_score = min_score_override if min_score_override is not None else rule.min_score
    if score < min_score:
        return None, f"综合分过低：{score} < {min_score}"

    confidence = _confidence_for_score(score)
    reason = _build_reason(
        rule,
        candidate,
        total_hits,
        exact_hits,
        context_hits,
        location_hits,
        author_include_hits,
        author_level_hits,
        focus_author_hits,
        score,
    )
    return SignalMatch(
        store_id=rule.store_id,
        store_name=rule.store_name,
        platform=rule.platform,
        content_id=candidate.content_id,
        url=candidate.url,
        title=candidate.title,
        poi_name=candidate.poi_name,
        author_name=candidate.author_name,
        author_level=candidate.author_level,
        verified_label=candidate.verified_label,
        follower_count=candidate.follower_count,
        author_tags=candidate.author_tags,
        ip_location=candidate.ip_location,
        topic_tags=candidate.topic_tags,
        published_at=candidate.published_at,
        like_count=candidate.like_count,
        favorite_count=candidate.favorite_count,
        comment_count=candidate.comment_count,
        share_count=candidate.share_count,
        score=score,
        confidence=confidence,
        matched_terms=matched_terms,
        matched_fields=matched_fields,
        focus_author_hits=sorted({term for values in focus_author_hits.values() for term in values}),
        reason=reason,
        raw_payload=candidate.raw_payload,
    ), None


def _score_match(
    rule: SignalRule,
    candidate: SignalCandidate,
    hits: dict[str, list[str]],
    exact_hits: dict[str, list[str]],
    context_hits: dict[str, list[str]],
    location_hits: dict[str, list[str]],
    author_include_hits: dict[str, list[str]],
    author_level_hits: dict[str, list[str]],
    focus_author_hits: dict[str, list[str]],
) -> int:
    score = 0
    unique_terms = {term for values in hits.values() for term in values}
    score += len(unique_terms) * 2
    exact_terms = {term for values in exact_hits.values() for term in values}
    score += len(exact_terms) * 2
    if rule.store_name in hits.get("poi_name", []):
        score += 4
    if rule.store_name in hits.get("title", []):
        score += 3
    if exact_hits.get("poi_name"):
        score += 4
    if exact_hits.get("title"):
        score += 3
    if "content" in hits:
        score += 1
    if len(hits) >= 2:
        score += 1
    if context_hits:
        score += min(3, len({term for values in context_hits.values() for term in values}))
    if location_hits:
        score += min(2, len({term for values in location_hits.values() for term in values}))
    if author_include_hits:
        score += 2
    if author_level_hits:
        score += 2
    if focus_author_hits:
        score += 5
    if candidate.verified_label:
        score += 1
    if candidate.follower_count >= 100000:
        score += 3
    elif candidate.follower_count >= 10000:
        score += 2
    elif candidate.follower_count >= 1000:
        score += 1
    if rule.require_poi and candidate.poi_name:
        score += 2
    score += _engagement_bonus(candidate)
    score += _freshness_bonus(candidate)
    return score


def _build_reason(
    rule: SignalRule,
    candidate: SignalCandidate,
    hits: dict[str, list[str]],
    exact_hits: dict[str, list[str]],
    context_hits: dict[str, list[str]],
    location_hits: dict[str, list[str]],
    author_include_hits: dict[str, list[str]],
    author_level_hits: dict[str, list[str]],
    focus_author_hits: dict[str, list[str]],
    score: int,
) -> str:
    fragments: list[str] = []
    if rule.store_name in hits.get("poi_name", []):
        fragments.append("POI 命中门店名")
    if rule.store_name in hits.get("title", []):
        fragments.append("标题直接提到门店")
    if exact_hits:
        fragments.append("命中门店强锚点")
    if any(term in hits.get("content", []) for term in rule.include_keywords):
        fragments.append("正文命中门店规则词")
    if context_hits:
        fragments.append("命中餐饮/探店上下文")
    if location_hits:
        fragments.append("命中门店位置上下文")
    if len(hits) >= 2:
        fragments.append("多字段同时命中")
    if author_include_hits:
        fragments.append("作者命中白名单")
    if author_level_hits:
        fragments.append("作者级别命中白名单")
    if focus_author_hits:
        fragments.append("命中重点达人名单")
    if candidate.verified_label:
        fragments.append("作者存在认证信息")
    if candidate.follower_count >= 1000:
        fragments.append(f"粉丝量{candidate.follower_count}")
    freshness_fragment = _freshness_reason(candidate)
    if freshness_fragment:
        fragments.append(freshness_fragment)
    heat_fragment = _engagement_reason(candidate)
    if heat_fragment:
        fragments.append(heat_fragment)
    if not fragments:
        fragments.append("规则命中")

    label = candidate.title or candidate.url or candidate.content_id
    return f"{label}；{'，'.join(fragments)}；综合分={score}"


def _find_hits(terms: list[str], field_values: dict[str, str]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    normalized_pairs = [(term, _normalize_text(term)) for term in terms if term.strip()]
    for field, value in field_values.items():
        normalized_value = _normalize_text(value)
        if not normalized_value:
            continue
        field_hits = []
        for raw_term, normalized_term in normalized_pairs:
            if normalized_term and normalized_term in normalized_value:
                field_hits.append(raw_term)
        if field_hits:
            hits[field] = field_hits
    return hits


def _merge_hits(*groups: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for group in groups:
        for field, terms in group.items():
            bucket = merged.setdefault(field, [])
            for term in terms:
                if term not in bucket:
                    bucket.append(term)
    return merged


def _collapse_ambiguous_matches(
    matches: list[SignalMatch],
    candidates: list[SignalCandidate],
    allow_ambiguous: bool,
) -> tuple[list[SignalMatch], list[SignalRejection]]:
    if allow_ambiguous:
        return matches, []

    grouped: dict[tuple[str, str], list[SignalMatch]] = {}
    for match in matches:
        grouped.setdefault((match.platform, match.content_id), []).append(match)

    resolved: list[SignalMatch] = []
    ambiguous_rejections: list[SignalRejection] = []
    candidate_index = {item.content_id: item for item in candidates}
    for items in grouped.values():
        items.sort(key=lambda item: (-item.score, item.store_id))
        best = items[0]
        if len(items) == 1:
            resolved.append(best)
            continue

        second = items[1]
        if second.score >= best.score - AMBIGUOUS_MARGIN:
            candidate = candidate_index.get(best.content_id)
            if candidate is not None:
                store_names = " / ".join(item.store_name for item in items[:2])
                ambiguous_rejections.append(
                    SignalRejection(
                        store_id=best.store_id,
                        store_name=best.store_name,
                        platform=best.platform,
                        content_id=best.content_id,
                        url=best.url,
                        title=best.title,
                        poi_name=best.poi_name,
                        author_name=best.author_name,
                        author_level=best.author_level,
                        verified_label=best.verified_label,
                        follower_count=best.follower_count,
                        author_tags=best.author_tags,
                        ip_location=best.ip_location,
                        topic_tags=best.topic_tags,
                        published_at=best.published_at,
                        like_count=best.like_count,
                        favorite_count=best.favorite_count,
                        comment_count=best.comment_count,
                        share_count=best.share_count,
                        reason=f"门店歧义冲突：{store_names}",
                        raw_payload=candidate.raw_payload,
                    )
                )
            continue
        resolved.append(best)

    return resolved, ambiguous_rejections


def _build_rejection(rule: SignalRule, candidate: SignalCandidate, reason: str) -> SignalRejection:
    return SignalRejection(
        store_id=rule.store_id,
        store_name=rule.store_name,
        platform=candidate.platform,
        content_id=candidate.content_id,
        url=candidate.url,
        title=candidate.title,
        poi_name=candidate.poi_name,
        author_name=candidate.author_name,
        author_level=candidate.author_level,
        verified_label=candidate.verified_label,
        follower_count=candidate.follower_count,
        author_tags=candidate.author_tags,
        ip_location=candidate.ip_location,
        topic_tags=candidate.topic_tags,
        published_at=candidate.published_at,
        like_count=candidate.like_count,
        favorite_count=candidate.favorite_count,
        comment_count=candidate.comment_count,
        share_count=candidate.share_count,
        reason=reason,
        raw_payload=candidate.raw_payload,
    )


def _build_rejection_section(rejections: list[SignalRejection]) -> list[str]:
    lines = [
        "",
        "## 已过滤噪音样例",
        "",
        "| 平台 | 标题 | 作者 | 时间 | 热度 | 过滤原因 |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for item in rejections[:8]:
        heat = _engagement_summary(item)
        title = _markdown_cell(item.title or item.url or item.content_id)
        author_bits = [item.author_name or "-"]
        if item.author_level:
            author_bits.append(item.author_level)
        if item.verified_label:
            author_bits.append(item.verified_label)
        if item.ip_location:
            author_bits.append(item.ip_location)
        author = _markdown_cell(" / ".join(author_bits))
        published_at = _markdown_cell(item.published_at or "-")
        reason = _markdown_cell(item.reason)
        lines.append(
            f"| {item.platform} | {title} | {author} | {published_at} | {heat} | {reason} |"
        )
    return lines


def _engagement_bonus(candidate: SignalCandidate) -> int:
    total = _engagement_score(candidate)
    if total >= 500:
        return 3
    if total >= 100:
        return 2
    if total >= 20:
        return 1
    return 0


def _freshness_bonus(candidate: SignalCandidate) -> int:
    published_at = _parse_datetime(candidate.published_at)
    if published_at is None:
        return 0
    now = datetime.now(published_at.tzinfo)
    hours = (now - published_at).total_seconds() / 3600
    if hours < 0:
        return 0
    if hours <= 2:
        return 3
    if hours <= 12:
        return 2
    if hours <= 24:
        return 1
    return 0


def _freshness_reason(candidate: SignalCandidate) -> str:
    bonus = _freshness_bonus(candidate)
    if bonus == 3:
        return "2小时内新内容"
    if bonus == 2:
        return "12小时内新内容"
    if bonus == 1:
        return "24小时内新内容"
    return ""


def _engagement_reason(candidate: SignalCandidate) -> str:
    bonus = _engagement_bonus(candidate)
    if bonus == 3:
        return "热度高"
    if bonus == 2:
        return "热度中高"
    if bonus == 1:
        return "已有初始互动"
    return ""


def _kol_tier(candidate: SignalCandidate | SignalMatch | SignalRejection) -> str:
    follower_count = int(getattr(candidate, "follower_count", 0))
    verified_label = str(getattr(candidate, "verified_label", "")).strip()
    author_level = str(getattr(candidate, "author_level", "")).strip()
    author_tags = [str(item).strip() for item in getattr(candidate, "author_tags", [])]
    tier_text = " ".join([verified_label, author_level, *author_tags]).lower()
    if follower_count >= 100000 or verified_label:
        return "重点达人"
    if follower_count >= 10000 or any(token in tier_text for token in ("达人", "kol", "博主", "探店")):
        return "达人账号"
    return "普通账号"


def _confidence_for_score(score: int) -> str:
    if score >= 12:
        return "高置信"
    if score >= 8:
        return "中高置信"
    return "基础命中"


def _markdown_cell(value: str) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|").strip()
    return text or "-"


def _engagement_score(candidate: SignalCandidate | SignalMatch | SignalRejection) -> int:
    return (
        int(getattr(candidate, "like_count", 0))
        + int(getattr(candidate, "favorite_count", 0)) * 2
        + int(getattr(candidate, "comment_count", 0)) * 2
        + int(getattr(candidate, "share_count", 0)) * 3
    )


def _engagement_summary(candidate: SignalCandidate | SignalMatch | SignalRejection) -> str:
    parts = [f"点赞{int(getattr(candidate, 'like_count', 0))}"]
    if int(getattr(candidate, "favorite_count", 0)) > 0:
        parts.append(f"收藏{int(getattr(candidate, 'favorite_count', 0))}")
    parts.append(f"评论{int(getattr(candidate, 'comment_count', 0))}")
    parts.append(f"转发{int(getattr(candidate, 'share_count', 0))}")
    return " / ".join(parts)


def _ensure_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected list")
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_tag_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip().lstrip("#") for part in value.split() if part.strip()]
        return [item for item in items if item]
    if isinstance(value, list):
        normalized = []
        for item in value:
            text = str(item).strip().lstrip("#")
            if text:
                normalized.append(text)
        return normalized
    return []


def _normalize_text(value: str) -> str:
    return "".join(str(value).strip().lower().split())


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_non_negative_int(value: object) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
