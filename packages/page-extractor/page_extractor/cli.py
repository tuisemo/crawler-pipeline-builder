"""详情页采集 CLI 入口 (CLI entrypoint)."""

from __future__ import annotations

import argparse
import json
import sys
import uuid

from .service import DetailCollectionService
from .types import DetailCollectionRequest


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="网页详情页深度采集工具 (Page Extractor CLI).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # collect 命令
    collect = subparsers.add_parser("collect", help="采集单个详情页并生成任务空间。")
    collect.add_argument("--url", required=True, help="目标网页 URL")
    collect.add_argument("--task-id", required=False, help="任务 ID (若不填则根据 URL 自动生成)")
    collect.add_argument("--output-root", required=True, help="任务工作空间的根目录")
    collect.add_argument("--format", choices=["json"], default="json", help="输出格式 (默认 json)")
    collect.add_argument("--timeout", type=int, default=180, help="网络或 PDF 生成的超时秒数")
    collect.add_argument("--detector", choices=["auto", "heuristic", "readability"], default="auto", help="内容区域检测策略")
    collect.add_argument("--extractor", choices=["auto", "trafilatura", "basic"], default="auto", help="正文提取引擎策略")
    collect.add_argument("--load-strategy", choices=["smart", "networkidle", "domcontentloaded"], default="smart", help="页面加载策略")
    collect.add_argument("--save-markdown", action="store_true", default=False, help="是否保存 content.md")
    collect.add_argument("--save-html", action="store_true", default=False, help="是否保存格式化后的 HTML")
    collect.add_argument("--save-pdf", action="store_true", default=False, help="是否尝试生成 PDF 快照")
    collect.add_argument("--save-meta-json", action="store_true", default=False, help="是否为每个产物生成 .meta.json (默认不生成)")
    collect.add_argument("--download-attachments", action="store_true", default=False, help="是否开启附件扫描与下载")
    collect.add_argument("--headed", action="store_false", dest="headless", default=True, help="是否使用有头模式 (GUI 模式)")
    collect.add_argument("--xpath", default=None, help="手动指定内容区域的 XPath/CSS 选择器 (覆盖自动检测)")
    collect.add_argument("--extra-wait", type=float, default=0, help="页面加载后的额外等待秒数 (用于处理异步渲染)")
    collect.add_argument("--log-level", default="INFO", help="日志级别")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "collect":
        parser.error("不支持的命令")

    # 处理可选的任务 ID
    task_id = args.task_id
    if not task_id:
        # 基于 URL 生成确定的 UUID
        task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, args.url))

    # 封装请求对象
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
        save_meta_json=bool(args.save_meta_json),
        download_attachments=bool(args.download_attachments),
        headless=bool(args.headless),
        content_area_hint=args.xpath,
        extra_wait=args.extra_wait,
        log_level=args.log_level,
        format=args.format,
    )
    
    # 调用服务层执行采集
    summary = DetailCollectionService().collect(request)
    
    # 按照指定格式输出摘要
    if args.format == "json":
        print(json.dumps(summary.to_dict(), ensure_ascii=False))
        
    return 0 if summary.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
