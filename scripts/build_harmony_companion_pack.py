from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DELIVERABLES = [
    "01_单店交付页.md",
    "03_实时舆情看板.md",
    "04_系统使用说明.md",
    "16_鸿蒙端先看这里.md",
    "17_鸿蒙端怎么配合第一版部署.md",
    "18_鸿蒙端图文说明.html",
]


def build_pack(profile_name: str, bundle_name: str, zip_output: Path) -> Path:
    profile_dir = ROOT / "data" / "client_profiles" / profile_name
    deliverable_dir = ROOT / "deliverables" / profile_name
    staging_root = ROOT / "deliverables" / "_pack_build" / bundle_name

    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)

    for name in DELIVERABLES:
        src = deliverable_dir / name
        if not src.exists():
            continue
        dst = staging_root / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for name in ["single_store_deliverable.md", "signal_watchboard.md", "signal_report.txt"]:
        src = profile_dir / name
        if not src.exists():
            continue
        dst = staging_root / "latest_outputs" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    zip_output.parent.mkdir(parents=True, exist_ok=True)
    archive_base = zip_output.with_suffix("")
    if zip_output.exists():
        zip_output.unlink()
    shutil.make_archive(str(archive_base), "zip", root_dir=staging_root)
    shutil.rmtree(staging_root, ignore_errors=True)
    return zip_output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a HarmonyOS companion pack")
    parser.add_argument("--profile-name", default="shibaojie", help="Client profile name")
    parser.add_argument(
        "--bundle-name",
        default="shibaojie_harmony_companion_pack_20260308",
        help="Staging bundle directory name",
    )
    parser.add_argument(
        "--zip-output",
        default=str(Path.home() / "Downloads" / "shibaojie_harmony_companion_pack_20260308.zip"),
        help="Zip output path",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    zip_output = Path(args.zip_output).expanduser().resolve()
    result = build_pack(args.profile_name, args.bundle_name, zip_output)
    print("pack_ready=True")
    print(f"zip_output={result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
