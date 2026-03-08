from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUSTOMER_DELIVERABLES = [
    "01_单店交付页.md",
    "02_实时舆情交付说明.md",
    "03_实时舆情看板.md",
    "04_系统使用说明.md",
    "05_实时舆情报告.txt",
    "09_部署与运行说明.md",
    "12_零技术门店KPI监管接入清单.md",
    "13_一条命令验收跑通说明.md",
    "14_客户运行包先看这里.md",
    "15_老板只需要改这几个设置.md",
    "README.md",
]
CUSTOMER_PROFILE_ITEMS = [
    "client_usage_guide.md",
    "execution_board.md",
    "login_checklist.md",
    "login_inventory.local.json",
    "signal_delivery_explainer.md",
    "signal_report.txt",
    "signal_watchboard.md",
    "single_store_deliverable.md",
    "stores_registry.json",
    "store_signal_rules.json",
    "verification_plan.json",
    "signal_inputs",
    "snapshots",
]


def should_skip(path: Path) -> bool:
    parts = path.parts
    return "__pycache__" in parts or path.name.endswith(".pyc") or path.name.endswith(".egg-info")


def copy_item(src: Path, dst: Path) -> None:
    if should_skip(src):
        return
    if src.is_dir():
        shutil.copytree(
            src,
            dst,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.egg-info"),
        )
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def build_pack(profile_name: str, bundle_name: str, zip_output: Path) -> Path:
    profile_dir = ROOT / "data" / "client_profiles" / profile_name
    if not profile_dir.exists():
        raise FileNotFoundError(f"profile not found: {profile_dir}")

    staging_root = ROOT / "deliverables" / "_pack_build" / bundle_name
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)

    items = [
        ROOT / "pyproject.toml",
        ROOT / ".env.example",
        ROOT / "README.md",
        ROOT / "RUN_ME_FIRST.txt",
        ROOT / "1_先双击安装.command",
        ROOT / "2_再双击打开控制台.command",
        ROOT / "3_需要时再双击运行验收.command",
        ROOT / "1_先双击安装.bat",
        ROOT / "2_再双击打开控制台.bat",
        ROOT / "3_需要时再双击运行验收.bat",
        ROOT / "src" / "gb_monitor",
        ROOT / "scripts",
    ]

    for item in items:
        relative = item.relative_to(ROOT)
        copy_item(item, staging_root / relative)

    deliverable_dir = ROOT / "deliverables" / "shibaojie"
    for name in CUSTOMER_DELIVERABLES:
        copy_item(deliverable_dir / name, staging_root / "deliverables" / "shibaojie" / name)

    for name in CUSTOMER_PROFILE_ITEMS:
        copy_item(profile_dir / name, staging_root / "data" / "client_profiles" / profile_name / name)

    zip_output.parent.mkdir(parents=True, exist_ok=True)
    archive_base = zip_output.with_suffix("")
    if zip_output.exists():
        zip_output.unlink()
    shutil.make_archive(str(archive_base), "zip", root_dir=staging_root)
    shutil.rmtree(staging_root, ignore_errors=True)
    return zip_output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a customer self-run installer pack")
    parser.add_argument("--profile-name", default="shibaojie", help="Client profile name")
    parser.add_argument(
        "--bundle-name",
        default="shibaojie_customer_selfrun_pack_20260308",
        help="Staging bundle directory name",
    )
    parser.add_argument(
        "--zip-output",
        default=str(Path.home() / "Downloads" / "shibaojie_customer_selfrun_pack_20260308.zip"),
        help="Zip output path",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    zip_output = Path(args.zip_output).expanduser().resolve()
    result = build_pack(
        profile_name=args.profile_name,
        bundle_name=args.bundle_name,
        zip_output=zip_output,
    )
    print(f"pack_ready=True")
    print(f"zip_output={result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
