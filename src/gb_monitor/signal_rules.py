from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from gb_monitor.models import SignalCandidate, SignalMatch, SignalRule


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
        required_any_fields = _ensure_str_list(item.get("required_any_fields")) or [
            "title",
            "content",
            "poi_name",
        ]
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
                required_any_fields=required_any_fields,
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
                raw_payload=item,
            )
        )
    return candidates


def match_candidates(
    rules: list[SignalRule],
    candidates: list[SignalCandidate],
    min_score_override: int | None = None,
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

    matches = list(matches_by_key.values())
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
            f"- {item.store_name} / {item.platform} / 分数{item.score}: {title}"
        )
        lines.append(f"  命中字段: {', '.join(item.matched_fields)}")
        lines.append(f"  命中词: {', '.join(item.matched_terms)}")
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

    core_terms = [rule.store_name, *rule.include_keywords]
    required_hits = _find_hits(core_terms, {k: v for k, v in field_values.items() if k in rule.required_any_fields})
    if not required_hits:
        return None

    total_hits = _find_hits(core_terms, field_values)
    if not total_hits:
        return None

    matched_terms = sorted({term for hits in total_hits.values() for term in hits})
    matched_fields = sorted(total_hits)
    score = _score_match(rule, total_hits)
    min_score = min_score_override if min_score_override is not None else rule.min_score
    if score < min_score:
        return None

    reason = _build_reason(rule, candidate, total_hits, score)
    return SignalMatch(
        store_id=rule.store_id,
        store_name=rule.store_name,
        platform=rule.platform,
        content_id=candidate.content_id,
        url=candidate.url,
        title=candidate.title,
        score=score,
        matched_terms=matched_terms,
        matched_fields=matched_fields,
        reason=reason,
        raw_payload=candidate.raw_payload,
    )


def _score_match(rule: SignalRule, hits: dict[str, list[str]]) -> int:
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
    return score


def _build_reason(
    rule: SignalRule,
    candidate: SignalCandidate,
    hits: dict[str, list[str]],
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
