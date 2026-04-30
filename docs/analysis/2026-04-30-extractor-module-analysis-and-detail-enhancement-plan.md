## 背景与目标

本文分析独立模块 `D:\WorkSpace\Python\Mycelium\packages\extractor` 的实现原理，评估其与当前 `crawler-workflow` 系统的互补关系，并规划一份不涉及立即改造的增强方案文档。

本次工作的目标是：

1. 深入拆解 `extractor` 模块的分层设计、核心流程与关键实现策略。
2. 对照当前仓库在列表页采集、工作流编排、脚本生成、持久化与辅助分析方面的现状，识别能力空白。
3. 梳理可借鉴且值得产品化的功能点，形成优先级明确的增强规划。
4. 输出独立分析文档，作为后续需求拆分、方案评审和实施排期的基础。

本次不执行任何产品升级或代码改造。

---

## 一句话结论

`extractor` 不是一个“简单的详情页正文抽取器”，而是一个围绕详情页采集构建的独立采集子系统。它在以下四个方向上对当前系统有明显补位价值：

- 详情页主内容识别与正文提取
- 附件识别、下载、归档与元数据落盘
- 详情页 PDF 快照与任务工作空间管理
- 多策略回退、结构化日志、下载复用与产物治理

当前 `crawler-workflow` 更擅长“列表页可视化编排 + 列表数据结构化抽取 + 脚本生成”；而 `extractor` 更擅长“单个详情页的深度采集和产物归档”。两者的能力边界天然互补，适合通过“独立详情页增强层”而不是“把所有逻辑硬塞进现有列表工作流骨架”来整合。

---

## 当前系统现状摘要

当前仓库的主轴是列表页工作流：

- 入口和编排核心在 [backend/workflow/compiler.py](/D:/WY-DATASETS/sea-data/backend/workflow/compiler.py) 与 [backend/workflow/schemas.py](/D:/WY-DATASETS/sea-data/backend/workflow/schemas.py)
- 自动检测偏列表结构，在 [backend/extraction/auto_detector.py](/D:/WY-DATASETS/sea-data/backend/extraction/auto_detector.py)
- HTML 辅助抽取偏 LLM 提示上下文整理，在 [backend/extraction/html_extractor.py](/D:/WY-DATASETS/sea-data/backend/extraction/html_extractor.py)
- 持久化偏结构化记录落地，在 [backend/runtime/record_sinks.py](/D:/WY-DATASETS/sea-data/backend/runtime/record_sinks.py)
- 终态产物之一是可独立运行的 Playwright 采集脚本，在 [backend/workflow/codegen.py](/D:/WY-DATASETS/sea-data/backend/workflow/codegen.py)

当前系统已经具备：

- 列表项选择器检测
- 分页检测与脚本生成
- 字段级提取
- JSON/SQLite 结构化落地
- 生成脚本日志与分页前页级持久化

当前系统明显较弱或缺失的详情页能力：

- 单条记录详情页正文识别与 Markdown 抽取
- 附件发现、下载、并发与降级链路
- 下载型详情链接与 HTML 页面链接的预判分流
- 详情页 PDF 快照
- 任务级工作目录与文件型产物治理
- 详情页级元数据产物
- 详情页抓取结果与列表记录之间的关联模型

---

## `extractor` 模块整体架构

`extractor` 的包结构大致如下：

- `extractor/cli.py`
  命令行入口
- `extractor/application/service.py`
  应用服务层，请求对象、运行时配置、结果摘要映射
- `extractor/core/*`
  核心流程、类型、配置、浏览器会话、附件服务、工作空间、重试
- `extractor/detectors/*`
  主内容选择器检测策略
- `extractor/extractors/*`
  正文内容提取策略
- `extractor/downloader/*`
  多策略文件下载、并发下载、浏览器池
- `extractor/snapshot/pdf.py`
  详情页 PDF 快照
- `extractor/llm/*`
  LLM 适配与提示词
- `extractor/utils/*`
  附件判定、文件名解析、日志、元数据、TLS 容错

这是一个典型的“应用服务 + 流水线编排 + 策略组件 + 产物工作空间”的设计，而不是单纯的一组工具函数。

---

## `extractor` 的主流程拆解

主流程在 [extractor/core/pipeline.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/pipeline.py>) 的 `CollectorPipeline.collect()` 中，执行顺序非常清晰：

1. 创建任务工作空间
2. 预检查目标 URL 是否其实是一个直接下载链接
3. 如果是直接文件下载，则直接走下载与元数据落盘
4. 否则启动 Playwright 浏览器会话
5. 加载页面，处理 Cookie 同意框
6. 检测主内容区域 selector
7. 基于 selector 约束 HTML 提取范围
8. 生成 Markdown 正文
9. 生成页面 PDF 快照
10. 扫描并下载附件
11. 落任务级 metadata

这个流程的关键特征是：

- 先判定“是不是 HTML 页面”再进入浏览器阶段
- 把“主内容定位”和“正文提取”拆成两个独立可回退的阶段
- 所有产物都围绕任务目录统一落地
- 附件能力被视为详情页采集的一等能力，而不是附加脚本

这和当前系统“直接围绕列表记录提取结构化字段”形成了明显差异。

---

## 实现原理拆解

### 1. 应用服务层：薄编排、强边界

[extractor/application/service.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/application/service.py>) 负责：

- 将 CLI / 上层调用请求转为 `CollectorConfig`
- 配置日志和 LLM 客户端
- 触发 `CollectorPipeline`
- 将内部结果映射为共享摘要契约

值得借鉴的点：

- 把“运行时配置”和“采集流程”解耦
- 保留从内部 `CollectorResult` 到外部 summary contract 的映射层
- 这使得 CLI、批处理调度器、平台 API 都能复用同一个采集核心

对当前系统的启发：

- 如果未来引入详情页增强能力，不应该直接把逻辑塞进现有路由或脚本生成器里
- 更适合新增一个独立的 `DetailCollectionService` 风格服务层，作为后端详情采集入口

### 2. 类型与配置：围绕详情采集定义统一契约

[extractor/core/types.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/types.py>) 定义了：

- 页面加载策略 `PageLoadStrategy`
- 选择器检测策略 `DetectorStrategy`
- 正文提取策略 `ExtractorStrategy`
- `CollectorConfig`
- `DetectorResult` / `ExtractorResult` / `CollectorResult`

其中 `CollectorResult` 很关键，它不只描述“抽到了什么文字”，还包括：

- selector 和 selector 置信度
- 用了哪种 detector / extractor
- 产物列表
- 附件发现数 / 下载数
- 任务开始结束时间
- 错误信息

对当前系统的启发：

- 我们现有的工作流结果更偏“结构化 record”和执行日志
- 如果做详情页增强，需要新增“详情采集结果契约”，不能继续只用列表记录结构凑合
- 详情页结果至少应包含：
  - `detail_url`
  - `main_content_selector`
  - `selector_confidence`
  - `content_markdown_path`
  - `pdf_snapshot_path`
  - `attachments_manifest`
  - `detector_strategy`
  - `extractor_strategy`
  - `task_dir`
  - `error`

### 3. 工作空间模型：每个详情页一个任务目录

[extractor/core/workspace.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/workspace.py>) 的思路很值得借鉴：

- 每次采集生成唯一 `task_id`
- 为每个任务创建独立目录
- `content.md`、`page.pdf`、`attachments/`、`metadata.json` 都放在同一任务目录下
- 文件产物和任务元信息保持聚合

这解决了三个现实问题：

- 文件型产物不会和结构化记录混在一起
- 一次失败采集仍然能留下现场
- 详情页采集天然支持“重复抓取、多版本、多任务追踪”

对当前系统的启发：

- 当前系统的 JSON/SQLite 落地适合结构化记录，但不适合管理详情页文件产物
- 如果未来支持详情页增强，应增加“任务工作空间”层，而不是把 Markdown / PDF / 附件路径零散地塞进结构化输出里

### 4. 页面加载与浏览器会话：智能加载 + Cookie 处理

[extractor/core/browser_session.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/browser_session.py>) 提供：

- `BrowserSessionFactory`
- `PageNavigator`
- 智能加载策略：`networkidle` 失败时回退 `domcontentloaded`
- 常见 Cookie 弹窗处理
- 隐匿脚本、固定 locale/timezone/user-agent

这部分设计的价值不在于“反爬技巧多强”，而在于：

- 将页面可交互准备过程封装出来
- 给详情页采集一个稳定的启动阶段

对当前系统的启发：

- 当前系统在生成脚本时已有导航与分页等待，但没有“详情页采集启动器”的抽象
- 可借鉴出一个统一的详情页加载助手，用于：
  - 详情页预热
  - Cookie 处理
  - 文本渲染完成等待
  - 可选截图/PDF前页面清洗

### 5. 主内容定位：三层 detector 策略

#### 5.1 HeuristicDetector

[extractor/detectors/heuristic.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/detectors/heuristic.py>) 以规则评分定位正文区域，评分因子包括：

- 文本长度
- 段落数量
- 链接密度
- 语义标签加分
- class/id 内容关键词
- 子元素多样性
- 导航/页脚/广告关键词扣分

这是“无需模型、可稳定运行”的保底层。

#### 5.2 ReadabilityDetector

[extractor/detectors/readability.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/detectors/readability.py>) 虽然不是完整 Mozilla Readability 嵌入，但实现了类似的正文评分思想：

- 段落与句长
- class/id 正负关键词
- link density 扣分
- table 干扰扣分

这是介于纯启发式与 LLM 之间的第二层。

#### 5.3 LLMDetector

[extractor/detectors/llm.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/detectors/llm.py>) 用 LLM 从 HTML 片段中推断主内容 selector，并在不可用时回退启发式策略。

关键实现点：

- HTML 截断与 script/style 清洗
- Prompt 输出 JSON 契约
- 弱解析兜底
- selector 基本合法性检查

#### 5.4 AUTO 策略的价值

在 `CollectorPipeline._detect_selector()` 中，AUTO 模式按照：

- `LLM`
- `Readability`
- `Heuristic`

的顺序尝试，并以置信度阈值控制回退。

这是一种很成熟的“高效果优先、低成本兜底”的策略链。

对当前系统的启发：

- 当前系统的 `auto_detector` 强在列表项与分页，不适合详情页主内容识别
- 后续如果支持详情页增强，应把“详情页正文 selector 检测”单独建模，不能复用列表页 `item_selector` 逻辑
- 推荐引入 `detail_detector_strategy` 概念，保留 `auto / heuristic / readability / llm`

### 6. 正文提取：Trafilatura 优先，LLM 补位

正文提取器在：

- [extractor/extractors/trafilatura.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/extractors/trafilatura.py>)
- [extractor/extractors/llm.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/extractors/llm.py>)

设计策略是：

- 先用 `Trafilatura` 提取 Markdown
- 如果结果为空，再回退到 LLM 提取

其中两个细节很重要：

1. 提取前不是直接把整页 HTML 交给提取器，而是通过 `_build_extraction_input()` 先按 detector 输出的 selector 收缩范围。
2. `TrafilaturaExtractor` 会补齐 Markdown 中的相对图片链接。

这意味着 `extractor` 并不是“先找到 selector 然后仅用 selector 截图”，而是把 selector 作为“约束 HTML 输入范围”的控制变量，进一步提升提取纯度。

对当前系统的启发：

- 这是一个非常值得优先借鉴的模式
- 我们当前的 `html_extractor` 已经具备 HTML 片段清洗思路，但目标是 LLM 提示上下文，不是详情正文提取
- 后续详情页能力建议引入“selector-scoped extraction input”作为基础能力

### 7. PDF 快照：围绕主内容裁剪

[extractor/snapshot/pdf.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/snapshot/pdf.py>) 的做法是：

- 先校验 selector 是否匹配元素
- 在页面中临时隐藏与目标内容无关的兄弟节点和干扰区块
- 调用 `page.pdf()`
- 再恢复页面
- 如果失败，则回退全页 PDF

这个能力的价值不只是“导出 PDF”，而是：

- 给 Markdown 正文提供人工验收参照物
- 让详情页采集结果具备可审计性
- 在正文抽取不完美时仍保留页面证据

对当前系统的启发：

- 当前系统生成脚本后，用户很难对详情页正文抽取质量做离线校验
- PDF 快照是一个很适合做“详情页采集证据件”的增强功能

### 8. 附件发现：围绕主内容邻域扫描

[extractor/core/attachments.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/attachments.py>) 的附件扫描逻辑非常有借鉴意义。

它不是全页盲扫，而是：

- 以主内容 selector 为中心
- 扫描主内容区域内链接
- 扫描父级若干层
- 扫描相邻兄弟节点中的“附件/下载/file”等语义区域
- 再对 article/main/content 区域补扫

再结合以下判定方法：

- 扩展名判定
- URL 关键字判定
- 链接文本关键字判定
- 必要时通过 `HEAD` 的 `Content-Type` 复核

这说明它的设计认知是：

- 附件常常不在正文 DOM 内部，而在正文旁边或后面
- 全页下载扫描会引入大量噪声

对当前系统的启发：

- 当前系统几乎没有附件采集能力
- 如果未来做详情页采集，附件发现必须与主内容 detector 结合，而不是简单“页面所有 a[href] 里筛扩展名”

### 9. 附件下载：多策略降级链

[extractor/downloader/multi_strategy.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/downloader/multi_strategy.py>) 是该模块最有工程含量的部分之一。

下载链路是：

1. `requests`
2. Playwright `context.request`
3. Playwright `page` 触发真实下载

并带有：

- 指数退避
- 失败降级日志
- 文件大小上限
- 中间失败清理

这个设计非常适合真实世界附件下载，因为很多站点会遇到：

- 直接请求能下
- API 请求才能继承会话
- 必须经过点击或页面触发下载

对当前系统的启发：

- 附件下载不应只提供一种网络路径
- “多策略下载器”应作为独立基础设施，而不是写进某个节点的业务逻辑里

### 10. 浏览器池与并发下载：降低附件下载成本

#### 并发下载

[extractor/downloader/concurrent_download.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/downloader/concurrent_download.py>) 使用 `ThreadPoolExecutor` 并发下载附件，适合多附件详情页。

#### 浏览器池

[extractor/downloader/browser_pool.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/downloader/browser_pool.py>) 通过池化浏览器与 context，降低 Playwright Page 降级下载时的冷启动成本。

这两个能力在当前系统中都不存在。

对当前系统的启发：

- 如果详情页增强只停留在“正文抽取”，系统价值有限
- 真正提升业务可用性的，恰恰是这些附件下载基础设施

### 11. 文件名解析、归档与元数据

辅助能力散落在：

- [extractor/utils/attachment.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/utils/attachment.py>)
- [extractor/utils/file.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/utils/file.py>)
- [extractor/utils/metadata.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/utils/metadata.py>)

关键点包括：

- 兼容 `filename*=` / RFC 5987
- 对中文乱码与 URL 编码做修复
- 文件名 sanitization 与路径穿越防护
- 压缩包自动解压
- 对解压出的目标文件生成 meta 文件

这些细节很“工程”，但恰恰是让附件采集真正可用的部分。

对当前系统的启发：

- 如果未来支持附件下载，文件名与归档规则必须先抽象清楚
- 否则很快会在中文文件名、重复文件名、压缩包附件上出现大量线上问题

### 12. 日志、指标与链路上下文

[extractor/utils/logging.py](</D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/utils/logging.py>) 提供：

- 结构化 logger
- JSON 日志输出
- `task_id` 上下文传播
- 下载/任务指标计数
- 事件化日志

当前模块中这一套并非每个能力都用满，但设计方向非常清晰：

- 详情页采集是“任务”，不是单次函数调用
- 任务需要可观测性

对当前系统的启发：

- 我们当前生成脚本日志已经有基础，但后端服务层缺少“详情页任务级日志契约”
- 若引入详情页增强，建议服务层和脚本层都统一支持：
  - task_id
  - page_url / detail_url
  - selector_confidence
  - attachment_discovered_count
  - attachment_downloaded_count
  - extraction_strategy
  - artifact_paths

---

## `extractor` 中值得特别注意的优点与局限

### 优点

- 详情页主流程拆分清晰，便于独立集成
- 具备多策略回退思想，真实场景适应性强
- 文件产物治理完整，适合做“详情页采集任务”
- 附件能力成熟度高于大多数简单采集模块
- 工作空间与元数据体系对后续审计、回放和失败排查很友好

### 局限与注意点

- `AutocrawlerConfig` / `RetryPolicy` / `CircuitBreaker` 基础设施较完整，但当前主流程并未完全打通使用，属于“设计储备多于实际接线”
- LLM Prompt 与返回解析相对朴素，若直接产品化，需要更严格的输出约束和安全校验
- `ReadabilityDetector` 是“readability-like”，并非完整 Readability 引擎移植
- 任务产物组织偏 CLI/文件系统风格，若放进平台 API，需要增加产物索引与引用契约
- 目前整体更适合“单详情任务”，还没有天然对接“列表页批量详情采集流水线”

---

## 与当前系统的互补关系

### 当前系统擅长

- 列表页工作流建模
- 列表项和分页自动识别
- 字段级结构化抽取
- 可导出可编辑的 Playwright 采集脚本
- 结构化记录持久化（JSON / SQLite）

### `extractor` 擅长

- 单详情页深度采集
- 主内容 selector 识别
- 正文 Markdown 提取
- 详情页 PDF 快照
- 附件发现 / 下载 / 解压 / 元数据
- 任务级产物目录治理
- 文件下载降级链和浏览器池复用

### 互补结论

最合理的组合方式是：

- 继续保留当前系统作为“列表页编排与结构化记录主引擎”
- 引入一个“详情页增强引擎”处理单条记录的深采任务

也就是说，未来更像：

`列表页记录抽取 -> 发现 detail_url -> 触发详情页增强子流程 -> 产出 Markdown/PDF/附件/元数据 -> 回填详情摘要`

而不是：

`让当前 extract_field 节点直接承担正文抽取、PDF、附件、下载池等全部职责`

---

## 可借鉴功能点清单

以下按优先级拆分。

### P0：高价值、低耦合、适合先规划的能力

1. 详情页任务工作空间
   每个详情页生成独立目录，统一落 `content.md`、`page.pdf`、`attachments/`、`metadata.json`

2. 直接下载链接预判
   在进入 Playwright 前先判断 URL 是否为文件下载型资源

3. 主内容 selector 与正文提取解耦
   把“定位正文区域”和“抽取正文 Markdown”建成两个步骤

4. selector-scoped extraction input
   先缩小 HTML 作用域，再交给提取器或 LLM

5. 详情页任务级结构化日志
   统一 task_id、artifact、strategy、attachment_count 等信息

### P1：中期价值高、需要新增后端能力边界

1. Heuristic / Readability / LLM 三层详情 detector
2. Trafilatura 优先、LLM 兜底的正文提取器
3. 详情页 PDF 快照
4. 附件发现服务
5. 附件文件名解析与元数据落盘

### P2：工程收益大、但需要更谨慎产品化

1. 多策略附件下载链
2. 并发附件下载器
3. BrowserPool 降低下载冷启动
4. 压缩包解压与子文件 meta 生成
5. 指标与事件化日志

---

## 规划方案选项

### 方案 A：Assist 能力优先

思路：

- 先把详情页能力做成后端 assist / analyze 服务
- 用于给用户辅助识别主内容 selector、预览正文抽取结果、列出附件候选
- 暂不进入 DSL 执行主链

优点：

- 风险最小
- 适合快速验证详情页 detector / extractor 的质量
- 不会破坏当前执行器与脚本生成链

缺点：

- 只能“辅助”，不能形成完整业务闭环
- 文件型产物能力很难完全体现

适用阶段：

- 能力验证期

### 方案 B：独立详情采集服务层

思路：

- 在当前后端新增独立 `DetailCollectionService`
- 由列表记录、详情 URL 或 API 直接触发
- 详情结果与结构化记录分离，通过引用关联

优点：

- 架构最清晰
- 与 `extractor` 原始设计最契合
- 易于演进到批量详情增强

缺点：

- 需要新增结果契约、任务目录治理、API 面
- 初期比 Assist 方案重

适用阶段：

- 推荐主线方案

### 方案 C：直接塞进现有 DSL 节点体系

思路：

- 直接扩展节点，例如 `open_detail_page`、`extract_markdown`、`download_attachments`
- 让现有工作流引擎承担详情页产物链

优点：

- 产品表面一致性强

缺点：

- 会快速抬高现有 DSL、执行器、脚本生成器复杂度
- 文件产物与结构化记录混排
- 详情任务语义与列表任务语义会彼此污染

适用阶段：

- 不建议作为第一阶段

### 推荐结论

推荐采用：

1. 近期按方案 A 验证能力边界
2. 中期落到方案 B，形成独立详情采集服务层
3. 远期再考虑是否把其中部分能力映射回 DSL 节点

---

## 推荐增强蓝图

### 目标架构

建议在当前系统中新增一个“详情增强子域”，与现有 `workflow` 主域并列：

- `backend/detail/`
  - `service.py`
  - `pipeline.py`
  - `types.py`
  - `workspace.py`
  - `detectors/`
  - `extractors/`
  - `attachments/`
  - `downloader/`
  - `snapshot/`

这不是要照搬 `extractor` 的目录，而是借鉴其边界划分。

### 建议的结果模型

建议新增 `DetailCollectionResult`，至少包含：

- `status`
- `task_id`
- `detail_url`
- `task_dir`
- `content_markdown_path`
- `pdf_snapshot_path`
- `attachment_records`
- `selector`
- `selector_confidence`
- `detector_strategy`
- `extractor_strategy`
- `attachment_discovered_count`
- `attachment_downloaded_count`
- `started_at`
- `completed_at`
- `error`

### 与当前列表工作流的衔接方式

未来可以考虑三种触发方式：

1. 记录级后处理
   列表页采集后，针对包含 `detail_url` 的记录单独增强

2. 人工触发详情增强
   在 UI 或 API 上对某条记录点击“采详情”

3. 批量详情增强任务
   对某次列表采集结果批量发起详情页子任务

推荐优先顺序：

1. 人工触发单条详情增强
2. 批量详情增强
3. DSL 原生节点化

---

## 分阶段规划

### Phase 0：分析与接口准备

目标：

- 明确详情结果契约
- 明确工作空间与产物目录规范
- 明确详情页增强 API 输入输出

产出：

- 设计文档
- 数据契约文档
- UI/API 交互草案

### Phase 1：详情页正文能力最小闭环

目标：

- 支持输入 URL，得到：
  - 主内容 selector
  - 正文 Markdown
  - 详情任务目录
  - 任务级 metadata

范围：

- HeuristicDetector
- Readability-like detector
- Trafilatura extractor
- 结构化日志

暂不做：

- 附件下载
- PDF 快照
- LLM detector/extractor

### Phase 2：详情页证据件与附件能力

目标：

- 增加 PDF 快照
- 增加附件扫描
- 增加基本附件下载与文件名治理

范围：

- 附件链接提取
- 文件名解析
- 归档/解压
- 元数据文件生成

### Phase 3：高鲁棒性与批量化

目标：

- 引入多策略下载链
- 引入并发附件下载
- 引入浏览器池复用
- 支持详情增强批处理

### Phase 4：工作流和产品整合

目标：

- 把详情增强结果回填到当前系统的记录模型或任务视图
- 评估是否需要 DSL 原生节点支持

---

## 对当前系统最值得立即保留的设计原则

即使现在不改代码，后续方案评审也建议坚持以下原则：

1. 列表页和详情页能力分域
   列表页系统不要直接吞掉详情页全部职责

2. 文件型产物和结构化记录分开治理
   Markdown、PDF、附件不是普通 records

3. 详情页增强应是任务模型
   需要 task_id、workspace、artifacts、metadata

4. 正文 selector 检测与正文提取分两步
   便于回退、审计与质量诊断

5. 附件下载必须支持多策略
   单一路径很难覆盖真实站点

6. 所有详情页产物都要可审计
   至少保留 selector、策略、日志、PDF 或原始证据件之一

---

## 建议沉淀成产品能力的功能包

从产品与工程角度，建议将未来详情增强拆成 5 个功能包：

### 功能包 1：详情页正文增强

- 输入详情页 URL
- 自动识别主内容
- 输出 Markdown
- 返回 selector 与置信度

### 功能包 2：详情页证据快照

- 基于主内容裁剪 PDF
- 失败回退全页 PDF

### 功能包 3：附件发现与下载

- 识别附件链接
- 下载附件
- 解压归档
- 生成 meta

### 功能包 4：详情任务工作空间

- task_id
- task_dir
- artifacts
- metadata.json

### 功能包 5：详情增强调度与回填

- 单条详情增强
- 批量详情增强
- 将详情摘要关联回列表记录

---

## 风险与约束

### 架构风险

- 若过早把详情能力直接塞进 DSL，会显著提高执行器和代码生成复杂度
- 若不建立独立产物目录，文件型结果会难以管理

### 性能风险

- PDF 生成和附件下载会显著拉长任务时间
- 浏览器池和并发下载虽能提升性能，但也会提高系统复杂度

### 质量风险

- LLM detector / extractor 若无严格约束，容易输出不稳定 selector 或 Markdown
- 直接下载预判和附件 HEAD 校验需要考虑站点反爬与证书异常

### 产品风险

- 若没有把“详情增强结果”与“列表记录结果”明确建模，用户会看不懂任务产物属于谁

---

## 最终建议

综合评估，建议后续将 `extractor` 视为“详情页增强能力参考实现”，而不是“整包复制到当前项目”。

推荐借鉴顺序如下：

1. 借鉴其领域边界：独立详情采集服务层、任务工作空间、详情结果契约
2. 借鉴其正文主链：主内容 detector -> selector-scoped extraction -> Markdown extractor
3. 借鉴其证据件能力：PDF 快照
4. 借鉴其附件能力：附件发现、文件名治理、归档元数据
5. 最后再借鉴其高复杂度基础设施：多策略下载、并发下载、浏览器池

如果未来要把这套能力做进当前产品，最优路线不是“把 `extractor` 做成一个大节点”，而是：

- 先形成独立详情增强服务
- 再与当前列表工作流建立结果关联
- 最后评估是否需要节点化、脚本化和 UI 暴露

---

## 本文对应的关键源码参考

`extractor` 模块：

- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/application/service.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/pipeline.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/browser_session.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/attachments.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/core/workspace.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/detectors/heuristic.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/detectors/readability.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/detectors/llm.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/extractors/trafilatura.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/extractors/llm.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/downloader/multi_strategy.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/downloader/concurrent_download.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/downloader/browser_pool.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/snapshot/pdf.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/utils/logging.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/utils/attachment.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/utils/file.py`
- `D:/WorkSpace/Python/Mycelium/packages/extractor/extractor/utils/metadata.py`

当前系统对照参考：

- [backend/extraction/auto_detector.py](/D:/WY-DATASETS/sea-data/backend/extraction/auto_detector.py)
- [backend/extraction/html_extractor.py](/D:/WY-DATASETS/sea-data/backend/extraction/html_extractor.py)
- [backend/runtime/record_sinks.py](/D:/WY-DATASETS/sea-data/backend/runtime/record_sinks.py)
- [backend/workflow/compiler.py](/D:/WY-DATASETS/sea-data/backend/workflow/compiler.py)
- [backend/workflow/schemas.py](/D:/WY-DATASETS/sea-data/backend/workflow/schemas.py)
