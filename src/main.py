#!/usr/bin/env python3
"""Generate an English daily physics news brief."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from .ai import fallback_summary, gemini_summary
    from .common import ROOT, SOURCE_CONFIG, parse_simple_yaml, read_env_file
    from .fetch import collect_news
    from .markdown import build_post
except ImportError:
    from ai import fallback_summary, gemini_summary
    from common import ROOT, SOURCE_CONFIG, parse_simple_yaml, read_env_file
    from fetch import collect_news
    from markdown import build_post


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the daily Physics Brief post.")
    parser.add_argument(
        "--config",
        default=SOURCE_CONFIG,
        help="Path to source YAML file, relative to repo root unless absolute.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Use headline-only fallback instead of Gemini.",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=None,
        help="Maximum total bullet points across India and World sections. Default comes from settings.final_points_per_section or 5.",
    )
    return parser.parse_args()


def resolve_config_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def main() -> int:
    read_env_file()
    args = parse_args()
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        return 2

    config = parse_simple_yaml(config_path)
    settings = config.get("settings", {})
    points_total = args.points or int(settings.get("final_points_per_section", 5))

    items = collect_news(config)
    if not items:
        print("Warning: no fresh physics items found; creating fallback post.", file=sys.stderr)

    used_ai = False
    summary = ""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key and not args.no_ai:
        try:
            summary = gemini_summary(items, api_key, points_total, settings)
            used_ai = True
        except Exception as exc:
            print(f"Warning: Gemini failed; using fallback summary: {exc}", file=sys.stderr)

    if not summary:
        summary = fallback_summary(items, points_total, settings)

    post_path = build_post(summary, items, used_ai)
    print(f"Created: {post_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
