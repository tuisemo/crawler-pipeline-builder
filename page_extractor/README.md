# Page Extractor

`page_extractor` 是当前仓库中独立拆出的“页面采集工具”运行时子包。它面向 **单个详情页** 的深度采集，支持通过 CLI 命令直接调用，也可以作为批处理脚本的下游执行器被外部编排器调用。

当前定位：

- 不负责列表页采集
- 不负责数据库批量调度
- 不依赖运行时 LLM
- 专注单个详情页的正文、PDF、附件与任务产物工作空间

与平台内其他能力的关系：

- 列表页采集脚本负责把记录写入 SQLite
- `Generate Detail Batch Runner` 负责生成批量编排脚本
- `page-extractor` 负责执行单条详情页采集任务

## 主要能力

- 页面加载与 Cookie 弹窗处理
- 主内容区域 selector 检测
- selector-scoped 正文提取
- Markdown 产物生成
- 可选 PDF 快照
- 附件发现与下载
- 任务级工作空间、日志与元数据

## 安装

如果你在当前仓库内使用：

```bash
uv sync
```

如果你希望把 CLI 装到当前 Python 环境：

```bash
pip install -e .
```

安装后会暴露命令：

```bash
page-extractor
```

## Playwright 浏览器依赖

第一次使用前，建议确认 Playwright 浏览器已安装：

```bash
playwright install chromium
```

如果你已经通过当前项目的开发环境完成过 Playwright 初始化，通常不需要重复安装。

## CLI 入口

主命令：

```bash
page-extractor collect --url "https://example.com/detail/123" --task-id "task-001" --output-root "./detail-output" --format json --save-markdown
```

当前支持的主要参数：

- `--url`
  详情页 URL，必填
- `--task-id`
  外部传入的任务 ID，必填
- `--output-root`
  任务工作空间根目录，必填
- `--format`
  当前支持 `json`
- `--timeout`
  网络 / PDF 超时秒数
- `--detector`
  `auto | heuristic | readability`
- `--extractor`
  `auto | trafilatura | basic`
- `--load-strategy`
  `smart | networkidle | domcontentloaded`
- `--save-markdown`
  保存 `content.md`
- `--save-pdf`
  尝试生成 `page.pdf`
- `--download-attachments`
  开启附件扫描与下载目录
- `--log-level`
  日志级别

## 输出工作空间

每次调用会在 `output-root` 下创建一个以 `task-id` 命名的任务目录：

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

其中：

- `content.md`
  提取出的正文 Markdown
- `page.pdf`
  PDF 快照，只有在 `--save-pdf` 时尝试生成
- `summary.json`
  机器可读摘要
- `metadata.json`
  任务级元数据
- `attachments/`
  附件目录；开启附件模式时会创建
- `logs/collect.log`
  任务级采集日志

## stdout JSON 摘要

CLI 成功或失败时都会尽量输出一个 JSON 摘要，典型结构如下：

```json
{
  "status": "success",
  "task_id": "task-001",
  "detail_url": "https://example.com/detail/123",
  "task_dir": "/abs/path/to/detail-output/task-001",
  "result_summary_path": "/abs/path/to/detail-output/task-001/summary.json",
  "content_markdown_path": "/abs/path/to/detail-output/task-001/content.md",
  "pdf_snapshot_path": "/abs/path/to/detail-output/task-001/page.pdf",
  "attachments_dir": "/abs/path/to/detail-output/task-001/attachments",
  "attachment_discovered_count": 2,
  "attachment_downloaded_count": 1,
  "detail_cli_version": "0.1.0",
  "error_code": null,
  "error_message": null,
  "started_at": "2026-04-30 10:00:00",
  "completed_at": "2026-04-30 10:00:07"
}
```

常见 `error_code` 包括：

- `invalid_url`
- `timeout`
- `network_error`
- `collection_error`

## 使用示例

### 只采正文 Markdown

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-task-001" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown
```

### 正文 + PDF

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-task-002" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --save-pdf
```

### 正文 + PDF + 附件

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-task-003" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --save-pdf ^
  --download-attachments
```

### 通过 Python 模块方式调用

如果当前环境还没有安装 `page-extractor` 到 PATH，可以直接用模块方式：

```bash
python -m page_extractor.cli collect --url "https://example.com/detail/123" --task-id "detail-task-004" --output-root "./detail-output" --format json --save-markdown
```

这也是当前 `Generate Detail Batch Runner` 在本地开发与测试环境里推荐的调用方式之一。

## 与批处理脚本的配合方式

`page-extractor` 不负责从数据库取任务。它的典型上游是 `Generate Detail Batch Runner` 生成出来的批量编排脚本。

典型协作链路：

1. 列表页脚本把记录写入 SQLite
2. 批处理脚本从 SQLite 读取 `detail_url`
3. 批处理脚本调用：
   - `page-extractor collect ...`
4. `page-extractor` 写回任务产物
5. 批处理脚本把状态和产物路径写入 `detail_collection_tasks`

## 当前限制

当前版本虽然已经是独立运行时子包，但仍处于“第一阶段完整闭环”状态，后续还会继续增强：

- 更强的正文区域识别质量
- 更多站点的附件下载覆盖
- 更稳定的 PDF 质量与异常分支
- 更完整的真实站点 smoke fixtures

## 相关文档

- [docs/page-extractor-cli-guide.md](/D:/WY-DATASETS/sea-data/docs/page-extractor-cli-guide.md)
- [docs/page-extractor-publish-and-install.md](/D:/WY-DATASETS/sea-data/docs/page-extractor-publish-and-install.md)
- [docs/superpowers/specs/2026-04-30-detail-extractor-cli-contract-spec.md](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-extractor-cli-contract-spec.md)
