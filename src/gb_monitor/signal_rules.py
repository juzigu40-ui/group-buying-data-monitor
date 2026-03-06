from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from gb_monitor.models import SignalCandidate, SignalMatch, SignalRule

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
        exclude_keywords = _ensure_str_list(item.get("exclude_keywords"))
        required_all_keywords = _ensure_str_list(item.get("required_all_keywords"))
        required_any_fields = _ensure_str_list(item.get("required_any_fields")) or [
            "title",
            "content",
            "poi_name",
        ]
        author_include_keywords = _ensure_str_list(item.get("author_include_keywords"))
        author_exclude_keywords = _ensure_str_list(item.get("author_exclude_keywords"))
        min_score = int(item.get("min_score", 5))

        if not store_id or not store_name or not platform:
            raise ValueError(f"stores[{idx}] missing store_id/store_name/platform")

        rules.append(
            SignalRule(
                store_id=store_id,
                store_name=store_name,
                platform=platform,
                include_keywords=include_keywords,
                exclude_keywords=exclude_keywords,
                required_all_keywords=required_all_keywords,
                required_any_fields=required_any_fields,
                author_include_keywords=author_include_keywords,
                author_exclude_keywords=author_exclude_keywords,
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
                url=str(item.get("url", "")).strip(),
                published_at=_normalize_optional_text(item.get("published_at")),
                like_count=_normalize_non_negative_int(item.get("like_count")),
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
    matches_by_key: dict[tuple[str, str], SignalMatch] = {}
    for candidate in candidates:
        for rule in rules:
            if candidate.platform != rule.platform:
                continue
            match = _match_single(rule, candidate, min_score_override)
            if match is None:
                continue
            key = (rule.store_id, candidate.content_id)
            previous = matches_by_key.get(key)
            if previous is None or match.score > previous.score:
                matches_by_key[key] = match

    matches = _collapse_ambiguous_matches(list(matches_by_key.values()), allow_ambiguous=allow_ambiguous)
    matches.sort(key=lambda item: (-item.score, item.store_id, item.content_id))
    return matches


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
        if item.published_at:
            lines.append(f"  发布时间: {item.published_at}")
        if item.like_count or item.comment_count or item.share_count:
            lines.append(
                f"  热度: 点赞{item.like_count} / 评论{item.comment_count} / 转发{item.share_count}"
            )
        if item.url:
            lines.append(f"  链接: {item.url}")
        lines.append(f"  说明: {item.reason}")
    return "\n".join(lines)


def matches_to_json(matches: list[SignalMatch]) -> list[dict[str, object]]:
    return [asdict(item) for item in matches]


def _match_single(
    rule: SignalRule,
    candidate: SignalCandidate,
    min_score_override: int | None,
) -> SignalMatch | None:
    field_values = {
        "title": candidate.title,
        "content": candidate.content,
        "poi_name": candidate.poi_name,
        "author_name": candidate.author_name,
    }

    exclude_hits = _find_hits(rule.exclude_keywords, field_values)
    if exclude_hits:
        return None

    if rule.author_exclude_keywords:
        author_exclude_hits = _find_hits(rule.author_exclude_keywords, {"author_name": candidate.author_name})
        if author_exclude_hits:
            return None

    author_include_hits = _find_hits(rule.author_include_keywords, {"author_name": candidate.author_name})
    if rule.author_include_keywords and not author_include_hits:
        return None

    core_terms = [rule.store_name, *rule.include_keywords]
    required_hits = _find_hits(core_terms, {k: v for k, v in field_values.items() if k in rule.required_any_fields})
    if not required_hits:
        return None

    if rule.required_all_keywords:
        required_all_hits = _find_hits(rule.required_all_keywords, field_values)
        required_all_terms = {term for values in required_all_hits.values() for term in values}
        if any(term not in required_all_terms for term in rule.required_all_keywords):
            return None

    total_hits = _find_hits(core_terms, field_values)
    if not total_hits:
        return None

    matched_terms = sorted({term for hits in total_hits.values() for term in hits})
    matched_terms.extend(
        sorted({term for hits in author_include_hits.values() for term in hits if term not in matched_terms})
    )
    matched_fields = sorted(total_hits)
    if author_include_hits and "author_name" not in matched_fields:
        matched_fields.append("author_name")
    score = _score_match(rule, candidate, total_hits, author_include_hits)
    min_score = min_score_override if min_score_override is not None else rule.min_score
    if score < min_score:
        return None

    confidence = _confidence_for_score(score)
    reason = _build_reason(rule, candidate, total_hits, author_include_hits, score)
    return SignalMatch(
        store_id=rule.store_id,
        store_name=rule.store_name,
        platform=rule.platform,
        content_id=candidate.content_id,
        url=candidate.url,
        title=candidate.title,
        author_name=candidate.author_name,
        published_at=candidate.published_at,
        like_count=candidate.like_count,
        comment_count=candidate.comment_count,
        share_count=candidate.share_count,
        score=score,
        confidence=confidence,
        matched_terms=matched_terms,
        matched_fields=matched_fields,
        reason=reason,
        raw_payload=candidate.raw_payload,
    )


def _score_match(
    rule: SignalRule,
    candidate: SignalCandidate,
    hits: dict[str, list[str]],
    author_include_hits: dict[str, list[str]],
) -> int:
    score = 0
    unique_terms = {term for values in hits.values() for term in values}
    score += len(unique_terms) * 2
    if rule.store_name in hits.get("poi_name", []):
        score += 4
    if rule.store_name in hits.get("title", []):
        score += 3
    if "content" in hits:
        score += 1
    if len(hits) >= 2:
        score += 1
    if author_include_hits:
        score += 2
    score += _engagement_bonus(candidate)
    score += _freshness_bonus(candidate)
    return score


def _build_reason(
    rule: SignalRule,
    candidate: SignalCandidate,
    hits: dict[str, list[str]],
    author_include_hits: dict[str, list[str]],
    score: int,
) -> str:
    fragments: list[str] = []
    if rule.store_name in hits.get("poi_name", []):
        fragments.append("POI 命中门店名")
    if rule.store_name in hits.get("title", []):
        fragments.append("标题直接提到门店")
    if any(term in hits.get("content", []) for term in rule.include_keywords):
        fragments.append("正文命中门店规则词")
    if len(hits) >= 2:
        fragments.append("多字段同时命中")
    if author_include_hits:
        fragments.append("作者命中白名单")
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


def _collapse_ambiguous_matches(matches: list[SignalMatch], allow_ambiguous: bool) -> list[SignalMatch]:
    if allow_ambiguous:
        return matches

    grouped: dict[tuple[str, str], list[SignalMatch]] = {}
    for match in matches:
        grouped.setdefault((match.platform, match.content_id), []).append(match)

    resolved: list[SignalMatch] = []
    for items in grouped.values():
        items.sort(key=lambda item: (-item.score, item.store_id))
        best = items[0]
        if len(items) == 1:
            resolved.append(best)
            continue

        second = items[1]
        if second.score >= best.score - AMBIGUOUS_MARGIN:
            continue
        resolved.append(best)

    return resolved


def _engagement_bonus(candidate: SignalCandidate) -> int:
    total = candidate.like_count + candidate.comment_count * 2 + candidate.share_count * 3
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


def _confidence_for_score(score: int) -> str:
    if score >= 12:
        return "高置信"
    if score >= 8:
        return "中高置信"
    return "基础命中"


def _ensure_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected list")
    return [str(item).strip() for item in value if str(item).strip()]


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
