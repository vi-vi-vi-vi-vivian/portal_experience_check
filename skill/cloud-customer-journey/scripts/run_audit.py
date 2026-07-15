#!/usr/bin/env python3
"""Run the cloud customer journey audit workflow from step1 onward."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import re
import urllib.parse
from datetime import datetime
from pathlib import Path


STAGES = ["感知", "下单", "支付", "使用", "续费", "变更", "退订"]


def product_slug_from_url(url: str) -> str:
    stem = Path(urllib.parse.urlparse(url).path).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug or "product"


def run(cmd: list[str], cwd: Path, check: bool = True) -> int:
    print("+ " + " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=str(cwd), env=os.environ.copy())
    if check and result.returncode:
        raise SystemExit(result.returncode)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--site", choices=["cn", "intl"], default="intl")
    parser.add_argument("--wait-seconds", type=int, default=180)
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--output", default=None, help="Report output path. Defaults to report.html inside the run directory.")
    parser.add_argument("--output-root", default="../../output/web")
    parser.add_argument("--run-id", default=None, help="Run directory name. Defaults to current timestamp YYYYMMDD-HHMMSS.")
    parser.add_argument("--model-config", default=None, help="Shared provider config JSON passed to step4.")
    parser.add_argument("--models", default=None, help="Deprecated. Use --model-config or edit shared/model_providers.json.")
    parser.add_argument("--retries-per-model", type=int, default=None)
    parser.add_argument("--retry-sleep-seconds", type=float, default=None)
    parser.add_argument("--model-switch-sleep-seconds", type=float, default=None)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    scripts = Path(__file__).resolve().parent
    py = sys.executable
    slug = product_slug_from_url(args.url)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = root / output_root
    run_dir = output_root / slug / run_id
    stages_dir = run_dir / "stages"
    screenshots_dir = run_dir / "screenshots"
    for directory in [stages_dir, screenshots_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    crawl_result = run_dir / "_crawl.json"
    merged_analysis = run_dir / "audit.json"
    report_output = Path(args.output) if args.output else run_dir / "report.html"
    if not report_output.is_absolute():
        report_output = root / report_output

    run([py, str(scripts / "step1_check_tools.py")], root)
    run(
        [
            py,
            str(scripts / "step2_login_handler.py"),
            "--url",
            args.url,
            "--project-root",
            str(root),
            "--site",
            args.site,
            "--wait-seconds",
            str(args.wait_seconds),
        ],
        root,
    )
    run(
        [
            py,
            str(scripts / "step3_crawl_journey.py"),
            "--url",
            args.url,
            "--project-root",
            str(root),
            "--site",
            args.site,
            "--all",
            "--output",
            str(crawl_result),
            "--screenshot-dir",
            str(screenshots_dir),
        ],
        root,
    )

    if not args.skip_analysis:
        for stage in STAGES:
            analyze_cmd = [
                py,
                str(scripts / "step4_analyze_stage.py"),
                "--stage",
                stage,
                "--crawl-result",
                str(crawl_result),
                "--project-root",
                str(root),
                "--output",
                str(stages_dir / f"{stage}.json"),
            ]
            if args.models:
                analyze_cmd.extend(["--models", args.models])
            if args.model_config:
                analyze_cmd.extend(["--model-config", args.model_config])
            if args.retries_per_model is not None:
                analyze_cmd.extend(["--retries-per-model", str(args.retries_per_model)])
            if args.retry_sleep_seconds is not None:
                analyze_cmd.extend(["--retry-sleep-seconds", str(args.retry_sleep_seconds)])
            if args.model_switch_sleep_seconds is not None:
                analyze_cmd.extend(["--model-switch-sleep-seconds", str(args.model_switch_sleep_seconds)])
            run(analyze_cmd, root)
        run(
            [
                py,
                str(scripts / "step4_merge_analysis.py"),
                "--project-root",
                str(root),
                "--crawl-result",
                str(crawl_result),
                "--analysis-dir",
                str(stages_dir),
                "--output",
                str(merged_analysis),
            ],
            root,
        )

    run(
        [
            py,
            str(scripts / "step5_generate_report.py"),
            "--project-root",
            str(root),
            "--analysis",
            str(merged_analysis),
            "--crawl-result",
            str(crawl_result),
            "--output",
            str(report_output),
        ],
        root,
    )
    print(f"Run directory: {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
