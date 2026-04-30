# Page Extractor CLI Guide

## 概览

`page-extractor` 是当前工程中独立维护的页面采集工具，专门面向 **单个详情页任务**。它不是列表页工作流引擎，也不是批处理调度器，而是被批处理脚本或人工命令行直接调用的执行器。

适用场景：

- 人工验证单个详情页采集效果
- 被 `run_detail_batch.py` 之类的批处理脚本调用
- 在不启动前端的情况下快速获取详情页正文 / PDF / 附件产物

## 命令结构

```bash
page-extractor collect --url <DETAIL_URL> --task-id <TASK_ID> --output-root <DIR> --format json [options]
```

当前唯一主子命令：

- `collect`

## 必填参数

### `--url`

详情页 URL。

要求：

- 必须是 `http` 或 `https`
- 不能为空

### `--task-id`

外部传入的任务 ID。

建议：

- 在批处理模式下由上游统一生成
- 在手工模式下用有语义的名字，便于排查

### `--output-root`

任务产物工作空间根目录。

例如：

```bash
--output-root "./detail-output"
```

### `--format`

当前仅支持：

- `json`

这意味着 stdout 会尽量输出结构化 JSON 摘要，便于上游脚本消费。

## 常用可选参数

### `--timeout`

控制网络 / PDF 相关的超时秒数。

示例：

```bash
--timeout 180
```

### `--detector`

正文主内容定位策略：

- `auto`
- `heuristic`
- `readability`

推荐默认：

- `auto`

### `--extractor`

正文提取策略：

- `auto`
- `trafilatura`
- `basic`

推荐默认：

- `auto`

### `--load-strategy`

页面加载策略：

- `smart`
- `networkidle`
- `domcontentloaded`

推荐默认：

- `smart`

### `--save-markdown`

保存正文 Markdown 到 `content.md`。

### `--save-pdf`

尝试生成页面 PDF 快照到 `page.pdf`。

### `--download-attachments`

开启附件扫描与下载流程，并创建 `attachments/` 目录。

### `--log-level`

控制日志级别。

常见值：

- `INFO`
- `DEBUG`
- `WARNING`
- `ERROR`

## 典型示例

### 示例 1：只采正文

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-001" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown
```

### 示例 2：正文 + PDF

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-002" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --save-pdf
```

### 示例 3：正文 + PDF + 附件

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-003" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --save-pdf ^
  --download-attachments
```

### 示例 4：模块方式调用

```bash
python -m page_extractor.cli collect --url "https://example.com/detail/123" --task-id "detail-004" --output-root "./detail-output" --format json --save-markdown
```

适合场景：

- 当前环境尚未安装 `page-extractor` 到 PATH
- 本地开发 / CI / 批处理脚本测试

## 输出工作空间说明

每次执行的任务目录结构如下：

```text
<output-root>/
└── <task-id>/
    ├── content.md
    ├── page.pdf
    ├── summary.json
    ├── metadata.json
    ├── attachments/
    └── logs/
        └── collect.log
```

### `content.md`

正文 Markdown 结果。

只有在：

- `--save-markdown`

开启时才保证存在。

### `page.pdf`

页面 PDF 快照。

只有在：

- `--save-pdf`

开启且生成成功时才存在。

### `attachments/`

附件目录。

只要开启：

- `--download-attachments`

就会创建该目录，即使页面最终没有发现附件。

### `summary.json`

任务的机器可读摘要，适合批处理脚本消费。

### `metadata.json`

任务级元数据，适合排查和产物治理。

### `logs/collect.log`

当前任务的运行日志。

## stdout JSON 摘要说明

调用方应该优先读取 stdout 输出的 JSON，而不是解析日志文本。

示例：

```json
{
  "status": "success",
  "task_id": "detail-001",
  "detail_url": "https://example.com/detail/123",
  "task_dir": "/abs/path/to/detail-output/detail-001",
  "result_summary_path": "/abs/path/to/detail-output/detail-001/summary.json",
  "content_markdown_path": "/abs/path/to/detail-output/detail-001/content.md",
  "pdf_snapshot_path": "/abs/path/to/detail-output/detail-001/page.pdf",
  "attachments_dir": "/abs/path/to/detail-output/detail-001/attachments",
  "attachment_discovered_count": 0,
  "attachment_downloaded_count": 0,
  "detail_cli_version": "0.1.0",
  "error_code": null,
  "error_message": null,
  "started_at": "2026-04-30 10:00:00",
  "completed_at": "2026-04-30 10:00:08"
}
```

## 常见失败类型

### `invalid_url`

触发条件：

- URL 为空
- URL 不是 `http/https`

### `timeout`

触发条件：

- 网络请求或 PDF 生成超过超时阈值

### `network_error`

触发条件：

- 网络层失败
- 站点无响应
- HTTP 请求异常

### `collection_error`

触发条件：

- 其他运行时异常

## 推荐给上游调用方的使用方式

对于批处理脚本，不建议直接 import Python 模块并调用内部 service，而是统一用 CLI 契约调用：

```bash
page-extractor collect ...
```

或者：

```bash
python -m page_extractor.cli collect ...
```

原因：

- 契约更稳定
- 上下游边界更清晰
- 更利于后续独立发布

## 相关文档

- [page_extractor/README.md](/D:/WY-DATASETS/sea-data/page_extractor/README.md)
- [docs/page-extractor-publish-and-install.md](/D:/WY-DATASETS/sea-data/docs/page-extractor-publish-and-install.md)
