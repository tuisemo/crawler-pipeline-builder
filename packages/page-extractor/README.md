# Page Extractor

`page-extractor` 是一个独立的 CLI 工具，面向 **单个详情页** 的深度采集。支持通过命令行直接调用，也可以作为批处理脚本的下游执行器被外部编排器调用。

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
- JS 渲染增强（滚动 + MutationObserver DOM 稳定性检测）
- 主内容区域检测（BROAD / Readability / Heuristic 三种策略）
- selector-scoped 正文提取（Readability-lxml + Trafilatura 双引擎合并）
- Markdown 产物生成（含标题规范化、去装饰图片、链接修复）
- 可选 HTML 快照（content area 格式化后 HTML，pretty-print 缩进）
- 可选 PDF 快照（A4 / 自定义边距）
- 附件发现与下载（支持 .pdf/.doc/.xls/.zip 等 15 种扩展名，多策略并发）
- 直接文件下载识别（绕过浏览器，直接抓取 PDF/ZIP 等二进制文件）
- 任务级工作空间、日志与元数据

## 包结构

```
packages/page-extractor/
├── pyproject.toml                 # 独立包定义（hatchling wheel）
└── page_extractor/                # 源码目录
    ├── __init__.py
    ├── cli.py                     # CLI 入口
    ├── service.py                 # 应用服务层
    ├── types.py                   # 请求/响应类型、版本常量
    ├── workspace.py               # 旧版 workspace 工具（兼容层）
    ├── core/                      # 核心运行时
    │   ├── pipeline.py            # 主编排管道
    │   ├── browser_session.py     # Playwright 浏览器会话
    │   ├── attachments.py          # 附件提取服务
    │   ├── types.py               # CollectorConfig / CollectorResult
    │   └── workspace.py           # CollectionWorkspace 任务空间
    ├── detectors/                 # 内容区域检测器
    │   ├── base.py
    │   ├── broad.py               # 结构评分算法（主策略）
    │   ├── heuristic.py
    │   └── readability.py
    ├── extractors/                 # 正文提取器
    │   ├── base.py
    │   ├── readability_lxml.py     # Mozilla Readability 算法
    │   └── trafilatura.py          # trafilatura 回退
    ├── snapshot/
    │   └── pdf.py                  # PDF 快照生成
    ├── downloader/
    │   ├── multi_strategy.py      # 多策略下载器
    │   ├── concurrent_download.py
    │   └── browser_pool.py
    └── utils/
        ├── logging.py
        ├── file.py
        ├── metadata.py
        ├── attachment.py
        └── tls.py
```

## 安装

### 方式 1：通过 uv workspace（推荐）

在仓库根目录执行：

```bash
uv sync
```

此命令会自动安装 `page-extractor` 作为 workspace 成员，同时安装主项目 `crawler-workflow`。

### 方式 2：仅安装 page-extractor

如果只需要 CLI 工具，可以在仓库根目录执行：

```bash
uv pip install -e ./packages/page-extractor
```

安装后会暴露命令：

```bash
page-extractor
```

### 方式 3：模块方式调用（无需安装）

```bash
python -m page_extractor.cli collect --help
```

## 依赖说明

`page-extractor` 仅依赖以下包（不含主项目的 FastAPI、OpenAI 等）：

- `requests` — HTTP 请求
- `playwright` — 浏览器自动化
- `beautifulsoup4` — HTML 解析
- `lxml` — CSS 选择器与 HTML 树操作
- `cssselect` — CSS 选择器支持
- `readability-lxml` — Mozilla Readability 文章提取
- `trafilatura` — 正文提取

可选依赖（归档解压）：

```bash
uv pip install -e "packages/page-extractor[archive]"
```

包含 `rarfile` 和 `py7zr`。

## Playwright 浏览器依赖

第一次使用前，建议确认 Playwright 浏览器已安装：

```bash
playwright install chromium
```

如果你已经通过当前项目的开发环境完成过 Playwright 初始化，通常不需要重复安装。

## CLI 入口

主命令：

```bash
page-extractor collect --url "https://example.com/detail/123" --output-root "./detail-output" --format json --save-markdown
```

当前支持的主要参数：

- `--url`
  详情页 URL，必填
- `--task-id`
  外部传入的任务 ID。若不填，则根据 URL 自动生成确定性的 UUID（推荐）
- `--output-root`
  任务工作空间根目录，必填
- `--format`
  当前支持 `json`
- `--timeout`
  网络 / PDF 超时秒数（默认 180）
- `--detector`
  `auto | broad | heuristic | readability`（默认 `auto`，broad 优先）
- `--extractor`
  `auto | trafilatura | basic`（默认 `auto`，双引擎合并）
- `--load-strategy`
  `smart | networkidle | domcontentloaded`（默认 `smart`）
- `--save-markdown`
  保存 `content.md`（默认 `False`）
- `--save-html`
  保存 `content.html`（content area 范围格式化后的 HTML，默认 `False`）
- `--save-pdf`
  尝试生成 `page.pdf`（默认 `False`）
- `--download-attachments`
  开启附件扫描与下载目录（默认 `False`）
- `--xpath`
  XPath 或 CSS selector，覆盖算法检测（覆盖 `--detector` 结果）
- `--extra-wait`
  JS 渲染额外等待秒数（默认 0）
- `--log-level`
  日志级别（默认 `INFO`）

## 输出工作空间

每次调用会在 `output-root` 下创建一个以 `task-id` 命名的任务目录：

```
<output-root>/
└── <task-id>/
    ├── content.md
    ├── content.html
    ├── page.pdf
    ├── summary.json
    ├── metadata.json
    ├── attachments/
    │   └── <downloaded-files>...
    └── logs/
        └── collect.log
```

其中：

- `content.md`
  提取出的正文 Markdown；通过 `--save-markdown` 启用（默认关闭）
- `content.html`
  Content area 范围的 HTML 快照（pretty-print 格式化）；通过 `--save-html` 启用（默认关闭）
- `page.pdf`
  PDF 快照，只有在 `--save-pdf` 时尝试生成
- `summary.json`
  机器可读摘要（CLI stdout 同款 JSON）
- `metadata.json`
  任务级元数据，含 `CollectorResult.to_dict()` 全部字段
- `attachments/`
  附件目录；开启 `--download-attachments` 时创建
- `logs/collect.log`
  任务级采集日志（含滚动检测、DOM 稳定性检测详情）

## stdout JSON 摘要

CLI 成功或失败时都会输出一个 JSON 摘要，典型结构如下：

```json
{
  "status": "success",
  "task_id": "task-001",
  "detail_url": "https://example.com/detail/123",
  "task_dir": "D:\\output\\task-001",
  "result_summary_path": "D:\\output\\task-001\\summary.json",
  "content_markdown_path": "D:\\output\\task-001\\content.md",
  "content_html_path": "D:\\output\\task-001\\content.html",
  "pdf_snapshot_path": null,
  "attachments_dir": null,
  "attachment_discovered_count": 0,
  "attachment_downloaded_count": 0,
  "detail_cli_version": "0.1.0",
  "error_code": null,
  "error_message": null,
  "started_at": "2026-05-06 10:00:00",
  "completed_at": "2026-05-06 10:00:07"
}
```

常见 `error_code` 包括：

- `invalid_url` — URL 不是有效的 http/https 地址
- `timeout` — 网络或页面加载超时
- `network_error` — 请求异常
- `collection_error` — 采集过程中发生未预见的异常

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

### 正文 + HTML

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-task-002" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --save-html
```

### 正文 + PDF

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-task-003" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --save-pdf
```

### 正文 + PDF + 附件

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-task-004" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --save-pdf ^
  --download-attachments
```

### 指定内容区域 XPath（覆盖自动检测）

```bash
page-extractor collect ^
  --url "https://example.com/detail/123" ^
  --task-id "detail-task-005" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --xpath "//article[@class='post-content']"
```

### JS 渲染增强（extra_wait）

```bash
page-extractor collect ^
  --url "https://example.com/spa-detail/456" ^
  --task-id "detail-task-006" ^
  --output-root ".\\detail-output" ^
  --format json ^
  --save-markdown ^
  --extra-wait 5
```

### 通过 Python 模块方式调用

如果当前环境还没有安装 `page-extractor` 到 PATH，可以直接用模块方式：

```bash
python -m page_extractor.cli collect --url "https://example.com/detail/123" --task-id "detail-task-006" --output-root "./detail-output" --format json --save-markdown
```

这也是当前 `Generate Detail Batch Runner` 在本地开发与测试环境里推荐的调用方式之一。

## 与批处理脚本的配合方式

`page-extractor` 不负责从数据库取任务。它的典型上游是 `Generate Detail Batch Runner` 生成出来的批量编排脚本。

典型协作链路：

1. 列表页脚本把记录写入 SQLite
2. 批处理脚本从 SQLite 读取 `detail_url`
3. 批处理脚本调用 `page-extractor collect ...`
4. `page-extractor` 写回任务产物（`content.md`、`metadata.json`、`summary.json`）
5. 批处理脚本把状态和产物路径写入 `detail_collection_tasks`

直接文件下载：当 URL 指向 PDF/ZIP 等非 HTML 资源时，`page-extractor` 会绕过浏览器直接用 `requests` 下载并写入任务目录，无需启动 Playwright。

## 内部执行流程（pipeline.py）

```
collect(url)
  ├─ _check_direct_download()        # 非 HTML 资源直接下载返回
  └─ browser_session
       ├─ PageNavigator.load()        # Smart/DOMContentLoaded/NetworkIdle
       ├─ handle_cookie_consent()     # 常见 Cookie 弹窗自动关闭
       ├─ _enhance_js_rendering()     # 滚动 + DOM 稳定性检测 + extra_wait
       ├─ _detect_content_area()     # BROAD → Readability → Heuristic 降级
       ├─ _scope_html(xpath)          # 仅在内容区域内提取
       ├─ _extract_content()          # Readability-lxml + Trafilatura 双引擎合并
       ├─ snapshot_element()           # PDF 快照（同一 XPath）
       └─ AttachmentService           # 附件发现 + 浏览器下载
```

## 检测器策略说明

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| `broad`（默认） | 结构评分：文本密度 + 标题/段落/图片/表格计数 + 链接密度惩罚 | 通用详情页，主选 |
| `readability` | Mozilla Readability 算法 | 新闻、博客类页面 |
| `heuristic` | 启发式规则 | 前两者都弱时的保底 |
| `auto` | 优先 broad（confidence ≥ 0.2），否则 readability（confidence ≥ 0.3），再降级 heuristic | 默认推荐 |

检测结果产生一个 XPath 表达式，作为正文提取、PDF 快照、附件发现的单一依据。

## 提取器策略说明

`auto` 模式同时运行 Readability-lxml 和 Trafilatura，结果合并去重后输出。合并策略：

- 按 markdown 长度降序排列
- 逐行做语义去重（去除短重复行）
- 用 `---` 分隔符拼接

`basic` 仅使用 BeautifulSoup 的简单标签遍历，作为所有提取器都失效时的保底。

## PDF 配置

`--save-pdf` 依赖 `snapshot/pdf.py`，默认参数：

- 格式：`A4`
- 边距：`10mm`
- 截图范围：整个 `content_area` XPath 匹配的元素

可通过 `CollectorConfig.pdf_format` / `pdf_margin` 进一步定制。

## 附件支持格式

`.pdf` `.doc` `.docx` `.xls` `.xlsx` `.ppt` `.pptx` `.zip` `.rar` `.7z` `.tar` `.gz` `.csv` `.txt` `.rtf` `.odt` `.ods`

最大文件大小：500 MB（`CollectorConfig.max_file_size`）


