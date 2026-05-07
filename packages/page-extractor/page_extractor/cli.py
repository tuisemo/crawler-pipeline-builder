"""CLI entrypoint for the reference detail extractor."""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from .service import DetailCollectionService
from .types import DetailCollectionRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reference detail-page extraction CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect one detail page into a task workspace.")
    collect.add_argument("--url", required=True, help="Detail page URL")
    collect.add_argument("--task-id", required=False, help="Caller-provided task ID (auto-generated from URL if missing)")
    collect.add_argument("--output-root", required=True, help="Root directory for detail task workspaces")
    collect.add_argument("--format", choices=["json"], default="json", help="Stdout output format")
    collect.add_argument("--timeout", type=int, default=180, help="Network/PDF timeout in seconds")
    collect.add_argument("--detector", choices=["auto", "heuristic", "readability"], default="auto", help="Main-content detector strategy")
    collect.add_argument("--extractor", choices=["auto", "trafilatura", "basic"], default="auto", help="Content extractor strategy")
    collect.add_argument("--load-strategy", choices=["smart", "networkidle", "domcontentloaded"], default="smart", help="Page load strategy")
    collect.add_argument("--save-markdown", action="store_true", default=False, help="Persist extracted markdown")
    collect.add_argument("--save-html", action="store_true", default=False, help="Persist scoped HTML of the content area")
    collect.add_argument("--save-pdf", action="store_true", default=False, help="Attempt PDF snapshot generation")
    collect.add_argument("--download-attachments", action="store_true", default=False, help="Prepare attachments workspace")
    collect.add_argument("--xpath", default=None, help="XPath or CSS selector for main content area (overrides algorithmic detection)")
    collect.add_argument("--extra-wait", type=float, default=0, help="Extra seconds to wait for JS-rendered content after page load")
    collect.add_argument("--log-level", default="INFO", help="Log level")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "collect":
        parser.error("Unsupported command")

    task_id = args.task_id
    if not task_id:
        # Generate deterministic UUID based on URL
        task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, args.url))

    request = DetailCollectionRequest(
        url=args.url,
        task_id=task_id,
        output_root=args.output_root,
        timeout=args.timeout,
        detector_strategy=args.detector,
        extractor_strategy=args.extractor,
        page_load_strategy=args.load_strategy,
        save_markdown=bool(args.save_markdown),
        save_html=bool(args.save_html),
        save_pdf=bool(args.save_pdf),
        download_attachments=bool(args.download_attachments),
        content_area_hint=args.xpath,
        extra_wait=args.extra_wait,
        log_level=args.log_level,
        format=args.format,
    )
    summary = DetailCollectionService().collect(request)
    if args.format == "json":
        print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return 0 if summary.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
