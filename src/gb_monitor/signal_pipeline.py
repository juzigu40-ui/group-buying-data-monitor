from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gb_monitor.feishu import FeishuNotifier
from gb_monitor.schedule import should_run
from gb_monitor.signal_rules import (
    build_signal_dashboard,
    build_signal_report,
    load_signal_candidates,
    load_signal_rules,
    review_candidates,
)
from gb_monitor.storage import Storage


SIGNAL_TASK_NAME = "signal_watchboard"
ATTRIBUTION_METRIC_SPECS = [
    ("douyin", "traffic_impressions", "抖音曝光"),
    ("douyin", "realtime_transaction_amount", "抖音成交额"),
    ("douyin", "realtime_ticket_count", "抖音成单量"),
    ("meituan", "valid_orders", "美团有效单"),
    ("eleme", "valid_orders", "闪购有效单"),
    ("jdwm", "valid_orders", "京东有效单"),
]


@dataclass(slots=True)
class SignalPipelineResult:
    executed: bool
    mode: str
    now: datetime
    input_files: list[Path]
    candidate_count: int
    match_count: int
    rejection_count: int
    deduped_match_count: int
    delivered: bool
    dispatch_recorded: bool
    skipped_reason: str
    report_text: str
    board_text: str


def resolve_profile_signal_input_paths(profile_dir: Path) -> list[Path]:
    signal_dir = profile_dir / "signal_inputs"
    standard_paths = {
        "xiaohongshu": signal_dir / "public_xiaohongshu.json",
        "douyin": signal_dir / "public_douyin.json",
        "shipinhao": signal_dir / "public_shipinhao.json",
    }
    fallback_paths = {
        "xiaohongshu": profile_dir / "xiaohongshu_signal_candidates.json",
        "douyin": profile_dir / "douyin_signal_candidates.json",
        "shipinhao": profile_dir / "shipinhao_signal_candidates.json",
    }
    existing: list[Path] = []
    for platform in ["xiaohongshu", "douyin", "shipinhao"]:
        standard = standard_paths[platform]
        fallback = fallback_paths[platform]
        if standard.exists():
            existing.append(standard)
        elif fallback.exists():
            existing.append(fallback)
    demo_path = profile_dir / "signal_candidates_demo.json"
    if not existing and demo_path.exists():
        existing.append(demo_path)
    return existing


def load_profile_signal_candidates(profile_dir: Path) -> tuple[list[Path], list]:
    input_files = resolve_profile_signal_input_paths(profile_dir)
    merged: list = []
    for path in input_files:
        merged.extend(load_signal_candidates(path))
    return input_files, merged


def run_profile_signal_pipeline(
    profile_dir: Path,
    storage: Storage,
    notifier: FeishuNotifier,
    timezone: ZoneInfo,
    mode: str = "scheduled",
    notify: bool = False,
    mark_dispatched: bool = False,
    dedupe_hours: int = 24,
    min_score_override: int | None = None,
    attribution_window_hours: int = 2,
) -> SignalPipelineResult:
    if mode not in {"scheduled", "all"}:
        raise ValueError("mode must be 'scheduled' or 'all'")

    now = datetime.now(timezone)
    input_files, candidates = load_profile_signal_candidates(profile_dir)
    if not input_files:
        return SignalPipelineResult(
            executed=False,
            mode=mode,
            now=now,
            input_files=[],
            candidate_count=0,
            match_count=0,
            rejection_count=0,
            deduped_match_count=0,
            delivered=False,
            dispatch_recorded=False,
            skipped_reason="missing_signal_inputs",
            report_text=f"[{now:%Y-%m-%d %H:%M:%S}] 未找到舆情输入文件",
            board_text="# 门店实时舆情看板\n\n- 状态：未找到舆情输入文件\n",
        )

    last_success = storage.get_last_success(SIGNAL_TASK_NAME)
    if mode == "scheduled" and not should_run(now, "signal", last_success):
        return SignalPipelineResult(
            executed=False,
            mode=mode,
            now=now,
            input_files=input_files,
            candidate_count=len(candidates),
            match_count=0,
            rejection_count=0,
            deduped_match_count=0,
            delivered=False,
            dispatch_recorded=False,
            skipped_reason="outside_signal_schedule",
            report_text=f"[{now:%Y-%m-%d %H:%M:%S}] 当前不在舆情调度窗口",
            board_text="# 门店实时舆情看板\n\n- 状态：当前不在舆情调度窗口\n",
        )

    rules_path = profile_dir / "store_signal_rules.json"
    rules = load_signal_rules(rules_path)
    matches, rejections = review_candidates(
        rules=rules,
        candidates=candidates,
        min_score_override=min_score_override,
        allow_ambiguous=False,
    )
    filtered_matches = storage.filter_new_signal_matches(
        matches=matches,
        now=now,
        dedupe_hours=max(dedupe_hours, 0),
    )
    _annotate_attribution_observations(
        storage=storage,
        matches=filtered_matches,
        window_hours=max(attribution_window_hours, 1),
    )
    report_text = build_signal_report(now, filtered_matches)
    if matches and not filtered_matches:
        report_text += "\n所有命中内容都在去重窗口内，当前无新增派送。"
    board_text = build_signal_dashboard(now, filtered_matches, rejections)

    delivered = False
    dispatch_recorded = False
    if notify:
        delivered = notifier.send_text(report_text)
    if mark_dispatched or delivered:
        storage.record_signal_dispatches(dispatched_at=now, matches=filtered_matches)
        dispatch_recorded = True
    storage.set_last_success(SIGNAL_TASK_NAME, now)

    return SignalPipelineResult(
        executed=True,
        mode=mode,
        now=now,
        input_files=input_files,
        candidate_count=len(candidates),
        match_count=len(matches),
        rejection_count=len(rejections),
        deduped_match_count=len(filtered_matches),
        delivered=delivered,
        dispatch_recorded=dispatch_recorded,
        skipped_reason="",
        report_text=report_text,
        board_text=board_text,
    )


def _annotate_attribution_observations(
    storage: Storage,
    matches: list,
    window_hours: int,
) -> None:
    for match in matches:
        published_at = _parse_datetime(match.published_at)
        if published_at is None:
            continue

        observations: list[str] = []
        observed = False
        for platform, metric_key, label in ATTRIBUTION_METRIC_SPECS:
            before = storage.nearest_metric_value(
                store_id=match.store_id,
                platform=platform,
                metric_key=metric_key,
                pivot=published_at,
                direction="before",
                window_hours=window_hours,
            )
            after = storage.nearest_metric_value(
                store_id=match.store_id,
                platform=platform,
                metric_key=metric_key,
                pivot=published_at,
                direction="after",
                window_hours=window_hours,
            )
            if before is None or after is None:
                continue
            delta = after[0] - before[0]
            observed = True
            if delta > 0:
                observations.append(f"{label}+{_format_metric_delta(delta)}")

        if observations:
            match.attribution_summary = (
                f"发布后{window_hours}小时观察窗："
                + " / ".join(observations)
                + "（仅为相关波动观察，不代表精确归因）"
            )
        elif observed:
            match.attribution_summary = (
                f"发布后{window_hours}小时观察窗：未见明显正向波动（仅为相关波动观察，不代表精确归因）"
            )
        else:
            match.attribution_summary = (
                f"发布后{window_hours}小时观察窗：当前窗口数据不足，暂不能判断引流波动"
            )


def _format_metric_delta(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
