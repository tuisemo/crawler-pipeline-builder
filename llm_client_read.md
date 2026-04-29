# LLM Client 源码分析文档

## 概述

`llm_client.py` 是 crawler-workflow 项目的 LLM（大语言模型）客户端模块，负责与 OpenAI 兼容的 API（包括 vLLM）进行交互，为爬虫脚本生成提供 AI 能力支持。

---

## 1. 模块结构总览

```
llm_client.py
├── 辅助函数
│   └── _should_retry_without_response_format()  # 判断是否应在无响应格式下重试
├── 数据类
│   ├── LLMResponse     # LLM API 响应封装
│   └── LLMConfig       # LLM 提供者配置
├── 抽象基类
│   └── BaseLLMClient   # LLM 客户端抽象接口
├── 具体实现
│   ├── OpenAIClient    # OpenAI API 客户端（也兼容 vLLM）
│   └── VLLMClient      # vLLM 专用客户端
├── 工厂函数
│   ├── get_llm_client()    # 根据 provider 获取客户端
│   └── get_default_client() # 获取默认客户端
└── 系统提示词
    ├── CRAWLER_SYSTEM_PROMPT        # 爬虫生成系统提示词
    ├── FIELD_INFERENCE_PROMPT       # 字段推断提示词
    ├── SELECTOR_OPTIMIZATION_PROMPT  # 选择器优化提示词
    └── PAGINATION_ANALYSIS_PROMPT   # 分页分析提示词
```

---

## 2. 核心数据类

### 2.1 LLMResponse

```python
@dataclass
class LLMResponse:
    content: str           # 响应内容
    model: str = ""        # 使用的模型
    usage: dict[str, int] | None = None  # token 使用量
    finish_reason: str | None = None      # 完成原因
    error: str | None = None              # 错误信息
```

**用途**：封装 LLM API 返回的所有信息，提供统一的响应格式。

### 2.2 LLMConfig

```python
@dataclass
class LLMConfig:
    provider: str = "openai"   # 提供者类型
    api_key: str = ""          # API 密钥
    base_url: str = ""         # API 基础 URL
    model: str = "gpt-4"        # 模型名称
```

**用途**：从环境变量或 .env 文件加载配置。

---

## 3. 客户端实现

### 3.1 OpenAIClient

`OpenAIClient` 是主要的 API 客户端，支持 OpenAI 官方 API 及任何 OpenAI 兼容的端点（如 vLLM）。

#### 核心方法

**generate(prompt, **kwargs)**
```
流程说明：
1. 构建 OpenAI 客户端参数（api_key, base_url）
2. 生成唯一请求 ID 用于审计追踪
3. 调用 audit_event 记录请求开始
4. 构建 messages 格式（单条 user 消息）
5. 应用可选参数（max_tokens, response_format, temperature）
6. 发送 chat.completions.create 请求
7. 解析响应并封装为 LLMResponse
8. 记录响应审计日志
9. 异常处理：
   - 若因 response_format 导致错误，且 _should_retry_without_response_format 返回 True
   - 则移除 response_format 重试一次（用于某些不支持 JSON mode 的后端）
```

**generate_with_system(system, user, **kwargs)**
```
流程说明：
1. 与 generate() 类似，但构建 messages 时包含两条消息：
   - system: 系统角色消息
   - user: 用户角色消息
2. 适用于需要系统提示词引导的复杂任务
```

**重试机制说明**：

`_should_retry_without_response_format` 函数检测以下错误标记：
- "response_format"
- "json_object"
- "json schema" / "json_schema"
- "unsupported"
- "extra_forbidden"
- "extra inputs are not permitted"
- "unknown field"
- "unknown parameter"

当检测到这些错误时，会移除 `response_format` 参数后重试，解决某些后端（如 vLLM）不支持 `response_format: {type: "json_object"}` 的问题。

### 3.2 VLLMClient

继承自 `OpenAIClient`，专门针对 vLLM 后端做了配置优化：

```python
class VLLMClient(OpenAIClient):
    def __init__(self, ...):
        # vLLM 使用不同的环境变量读取优先级
        api_key = api_key or os.environ.get("API_TOKEN", "") or settings.api_token
        base_url = base_url or os.environ.get("API_BASE_URL", "") or settings.api_base_url
        model = model or os.environ.get("MODEL_NAME", "") or settings.model_name
```

---

## 4. 工厂函数

### 4.1 get_llm_client(provider, **kwargs)

```python
def get_llm_client(provider: str = "auto", **kwargs) -> BaseLLMClient
```

**流程**：
```
1. 若 provider == "auto"，从环境配置读取实际 provider
2. 根据 provider 类型返回对应客户端实例
   - "vllm" → VLLMClient
   - 其他 → OpenAIClient
```

### 4.2 get_default_client()

```python
def get_default_client() -> BaseLLMClient
```

**流程**：
```
1. 从环境配置加载 LLMConfig
2. 根据 config.provider 返回对应客户端实例
3. 传递完整的 api_key, base_url, model 参数
```

---

## 5. 系统提示词详解

### 5.1 CRAWLER_SYSTEM_PROMPT

**用途**：作为系统提示词，引导 LLM 生成完整可运行的 Playwright 爬虫脚本。

**工作流程**：

```
┌─────────────────────────────────────────────────────────────┐
│                    爬虫生成决策层级                           │
├─────────────────────────────────────────────────────────────┤
│ 1. 确定性执行计划和输出契约（最高优先级）                      │
│ 2. 已验证的选择器和显式字段模式                               │
│ 3. HTML 证据和页面特定样本                                   │
│ 4. 不冲突的编辑者备注或用户偏好                             │
│ 5. 通用爬虫启发式方法（最后手段）                            │
└─────────────────────────────────────────────────────────────┘
```

**关键要求流程**：

1. **Playwright Sync API 使用**
   ```
   要求 → 必须使用 sync_playwright
   ```

2. **分页处理流程**
   ```
   发现分页 → 适当等待 → 验证 → 保守停止条件
   ```

3. **持久化模式**
   ```
   根据输出契约的 persistence mode 发出记录
   - memory: 保留在内存
   - file: 保存到文件
   - sqlite: 保存到 SQLite
   ```

4. **ElementHandle vs Locator 决策**
   ```
   已有 ElementHandle 时 → 直接使用 query_selector/query_selector_all
   使用 Page/Frame 时 → 使用 locator()
   ```

5. **选择器保留策略**
   ```
   已验证选择器 → 除非明确无效/不兼容，否则保留
   未验证选择器 → 基于 HTML 证据谨慎生成
   ```

**最终自检清单**：
- [ ] 是否保留了确定性控制流？
- [ ] 是否保留了输出模式和持久化行为？
- [ ] 是否避免了 ElementHandle `.locator()` 误用？
- [ ] 是否保留了已验证选择器？
- [ ] 是否选择了满足计划的最简单实现？

---

### 5.2 FIELD_INFERENCE_PROMPT

**用途**：分析 HTML 片段，提取结构化字段选择器。

**执行流程**：

```
┌─────────────────────────────────────────────────────────────┐
│                    证据优先级排序                            │
├─────────────────────────────────────────────────────────────┤
│ 1. 重复的 DOM 结构（明确代表记录）                           │
│ 2. 稳定语义锚点（id、data 属性、列表容器、卡片、文章、标题）   │
│ 3. 字段特定线索（标签语义、类名、可见文本）                   │
│ 4. 通用标签（最后手段）                                      │
└─────────────────────────────────────────────────────────────┘
```

**字段提取流程**：

1. **item_selector 生成**
   ```
   要求 → 仅匹配重复列表项的 CSS 选择器
   策略 → 优先使用作用域路径：<ancestor> > <tag>.<stable-class>
   禁止 → 裸标签如 li、div（会匹配数百个无关元素）
   ```

2. **field_selector 生成**
   ```
   要求 → 相对于每个列表项元素（item 内评估，非全局）
   策略 → 使用 :scope > ... 或短相对路径
   禁止 → 裸通用选择器如 .title、.date（全局匹配过多）
   优化 → 添加最近稳定祖先前缀：div.card-body > span.date
   ```

3. **字段覆盖范围**
   ```
   必选字段：
   - title → 主标题或文章名（文本）
   - link → 主要锚点 URL（attr:href）
   
   可选字段：
   - publish_date → 发布/更新日期（文本）
   - summary → 摘要或描述（文本）
   - image → 缩略图（attr:src 或 attr:data-src）
   - source → 作者、分类或来源标签（文本）
   ```

**输出质量控制**：
- 目标每个 item 提取 3-6 个字段
- 优先每字段一个高置信度选择器，而非多个推测性替代方案
- 若页面证据仅支持 2 个强字段，返回 2 个而非凑够 6 个

---

### 5.3 SELECTOR_OPTIMIZATION_PROMPT

**用途**：优化给定的 CSS 选择器，提高全局无歧义性和对 DOM 变化的鲁棒性。

**优化决策流程**：

```
┌─────────────────────────────────────────────────────────────┐
│                    选择器优化步骤                            │
├─────────────────────────────────────────────────────────────┤
│ 1. 诊断歧义：统计当前选择器在页面上匹配的元素数量             │
│    → 若 > 预期 item 数量，则选择器过宽                       │
│                                                              │
│ 2. 逐级收敛：构建作用域路径                                  │
│    向上：DOM 树到最近稳定语义祖先                             │
│    向下：到达目标元素                                        │
│    好示例：section.news-container > ul > li.news-item        │
│    坏示例：.news-item（裸类，可能在其他地方出现）            │
│                                                              │
│ 3. 优先稳定属性：id（真正唯一）、稳定类名、data-*、语义标签   │
│                                                              │
│ 4. 修剪冗余：移除不增加区分度的中间节点                       │
│                                                              │
│ 5. 避免过度紧窄：不要产生脆弱、位置依赖或易零匹配的选择器     │
└─────────────────────────────────────────────────────────────┘
```

**失败策略**：
- 若初始选择器已是最佳稳定选择，保持不变并说明原因
- 不因追求简洁而牺牲稳定性
- 不改变选择器指向不同语义元素
- 不输出非 CSS 语法

---

### 5.4 PAGINATION_ANALYSIS_PROMPT

**用途**：分析 HTML 中的分页元素，提取高度鲁棒的选择器和分页策略。

**分析决策流程**：

```
┌─────────────────────────────────────────────────────────────┐
│                    证据优先级                                │
├─────────────────────────────────────────────────────────────┤
│ 1. 显式 next/load-more 语义                                   │
│    - rel="next"                                              │
│    - aria-label                                              │
│    - button 文本                                              │
│    - title 属性                                              │
│    - 稳定 next 特定类名                                       │
│                                                              │
│ 2. PAGINATION_CONTROL_SUMMARY（若存在）                      │
│                                                              │
│ 3. 分页容器结构和相对位置                                     │
│                                                              │
│ 4. 通用启发式（最后手段）                                     │
└─────────────────────────────────────────────────────────────┘
```

**分页策略识别流程**：

1. **识别分页容器和具体下一页/加载更多元素**

2. **确定分页策略类型**
   ```
   click_next      → 标准分页，有"下一页"按钮/链接
   infinite_scroll → 无按钮，滚动触发
   load_more       → 显式按钮追加内容
   none            → 未发现分页
   ```

3. **生成鲁棒选择器**
   ```
   next_button_selector 要求：
   - 必须仅指向具体下一页控制元素
   - 不得匹配：
     × 所有分页锚点或按钮
     × 所有页码按钮
     × 整个分页容器
   ```

4. **输出格式**
   ```json
   {
     "pagination_strategy": "click_next|infinite_scroll|load_more|none",
     "next_button_selector": "鲁棒 CSS 选择器",
     "page_number_selectors": ["页码选择器列表"],
     "reason": "选择原因说明",
     "confidence": 0.0-1.0
   }
   ```

**关键约束**：
- 页码选择器列表中不包含 next/load-more 选择器
- 无明显 next 控制时返回 `none` 而非猜测
- 区分页码按钮、当前页指示器、上一页按钮和真正的下一页控制
- 拒绝匹配多个分页锚点的宽泛选择器

---

## 6. 审计日志事件

模块使用 `audit_event` 记录以下事件：

| 事件类型 | 触发时机 | 记录内容 |
|---------|---------|---------|
| `llm_request` | API 请求发起 | request_id, model, temperature, max_tokens, prompt |
| `llm_response` | 请求成功 | content, usage, finish_reason |
| `llm_error` | 请求失败 | error 信息 |
| `llm_empty_choices` | 响应无 choices | model, method |
| `llm_response_format_retry` | 因格式错误重试 | error 信息 |

---

## 7. 典型调用示例

```python
from llm_client import get_default_client, CRAWLER_SYSTEM_PROMPT

# 获取默认客户端
client = get_default_client()

# 生成爬虫脚本
response = client.generate_with_system(
    system=CRAWLER_SYSTEM_PROMPT,
    user="请基于以下执行计划生成爬虫：\n{execution_plan}",
    temperature=0.2,
    max_tokens=4000
)

# 提取字段选择器
field_response = client.generate(
    prompt=FIELD_INFERENCE_PROMPT.format(html_fragment=html),
    response_format={"type": "json_object"}
)
```

---

## 8. 配置优先级

```
API 参数 > 环境变量 > settings 配置默认值
```

**环境变量映射**：

| 设置项 | OpenAI 模式 | vLLM 模式 |
|-------|-----------|----------|
| API Key | `OPENAI_API_KEY` | `API_TOKEN` |
| Base URL | `OPENAI_BASE_URL` | `API_BASE_URL` |
| Model | `MODEL_NAME` | `MODEL_NAME` |

---

## 9. 专家实战评估

### 9.1 评估说明

本章节引入两位虚拟专家角色，从不同维度对现有提示词和设计流程进行实战评估：

- **专家 A：精通 Playwright 的顶级数据采集脚本开发者**
  - 视角：脚本生成的正确性、可运行性、实战稳定性
  - 关注点：Playwright API 正确使用、ElementHandle vs Locator 决策、分页稳定性、输出持久化正确性

- **专家 B：提示词编写大师**
  - 视角：提示词结构、指令清晰度、边界情况处理、输出格式约束
  - 关注点：提示词是否会产生歧义、是否遗漏关键约束、是否有过度的推测性指令

---

### 9.2 选择器生成流程评估

#### 9.2.1 FIELD_INFERENCE_PROMPT 评估

**专家 A（Playwright 开发者）评语：**

> "字段推断流程整体设计合理，但存在几个实战中的痛点。"

**问题 1：item_selector 与 field_selector 作用域解释不够明确**

当前提示词要求 field_selector "relative to each list item element (evaluated inside the item)"，但 LLM 在实践中经常生成全局作用域的选择器。

**实战案例**：
```html
<!-- 页面结构 -->
<div class="news-list">
  <article class="item">
    <h3 class="title">Article Title</h3>
    <a class="link" href="/article/1">Read more</a>
  </article>
  <article class="item">
    <h3 class="title">Another Title</h3>
    <a class="link" href="/article/2">Read more</a>
  </article>
</div>
<div class="sidebar">
  <h3 class="title">Sidebar Title</h3>  <!-- 干扰项 -->
</div>
```

LLM 可能生成 `.title` 而非 `article.item > h3.title`，因为它看到多个 `.title` 存在。

**改进建议**：
在提示词中增加明确的"干扰项示例"段落：
```
Page also contains:
- Sidebar elements with class "title" that are NOT part of the list items
- Navigation items with class "link" that are NOT the primary article links
Your field selectors MUST NOT match these interference elements.
```

**问题 2：HTML 截断策略存在信息丢失风险**

当前 `assist_services.py` 中 HTML 被截断到 6000 字符：
```python
html = (request.html_fragment or "")[:6000]
```

这可能导致：
- 列表开头有复杂 header 和导航，截断后丢失真正的列表结构
- 列表末尾的分页按钮被截断，无法正确分析分页策略

**改进建议**：
改为保留 HTML 的首尾两端（各 3000 字符），中间用占位符标注：
```
<!-- ... {estimated_item_count} more items with similar structure ... -->
```

**问题 3：image 字段的 src vs data-src 处理不足**

提示词对 image 字段的处理：
```
'image' — thumbnail image if present (attr:src or attr:data-src)
```

但现代网页常用：
- `data-src`（懒加载）
- `data-lazy-src`
- `data-original`
- `src` 为占位图（如 1x1 pixel），真实图片在 `data-src`

**改进建议**：
增强对现代图片懒加载模式的支持：
```
For image fields, check these attributes in order of reliability:
1. data-src (most reliable for lazy-loaded images)
2. data-lazy-src
3. data-original
4. src (only if it doesn't look like a placeholder - check for 1x1, blank, or generic pixel patterns)
5. data-srcset or srcset for responsive images
```

**专家 B（提示词大师）评语：**

> "提示词结构良好，但约束条件分散在多处，容易被 LLM 选择性忽略。"

**结构性问题**：FIELD_INFERENCE_PROMPT 中存在多层嵌套约束：
1. "Selector Precision Rules" 中的 item_selector 规则
2. "Field Decision Rules" 中的字段选择规则
3. "Failure Policy" 中的兜底策略

LLM 在生成长输出时，容易忽略后期约束。

**改进建议**：
将所有约束浓缩为强制性的"自检清单"，要求 LLM 在输出 JSON 之前先验证：
```
Before returning your JSON output, explicitly verify:
- [ ] item_selector matches ONLY the repeating list items, not sidebar/header/footer
- [ ] Each field_selector is scoped to within the item element
- [ ] No field_selector uses bare generic selectors (.title, .content, .item)
- [ ] image selector handles lazy-loaded images (data-src, etc.)
```

---

#### 9.2.2 SELECTOR_OPTIMIZATION_PROMPT 评估

**专家 A（Playwright 开发者）评语：**

> "选择器优化流程的设计思路正确，但缺少对优化结果的"可执行性"验证。"

**核心问题：优化后的选择器可能破坏 Playwright 兼容性**

当前提示词要求优化后的选择器：
```
MUST be a standard CSS selector compatible with querySelector / querySelectorAll and Playwright locator()
```

但优化过程中可能产生：
- 包含 `:scope` 的选择器在某些 Playwright 上下文中有歧义
- XPath 被意外转换成 CSS 后失去语义准确性
- 正则表达式丰富的属性选择器（如 `a[href^="..."]`）在某些旧版 Playwright 中支持不一致

**改进建议**：
增加"优化安全边界"约束：
```
Optimization Safety Boundary:
- If the initial selector uses XPath, keep it as XPath unless it is clearly broken
- Do not convert a[href^="..."] style selectors to equivalent CSS regex patterns that some backends don't support
- Keep optimized selectors simple: tag.class is preferred over deeply nested structures
- If optimization would require pseudo-selectors (:nth-child, :first-of-type), prefer adding a stable class instead
```

**专家 B（提示词大师）评语：**

> "选择器优化的决策树不够清晰，导致优化策略不稳定。"

**问题**：提示词中说：
```
- If the current selector is already the best stable choice, keep it.
```

但没有给出"什么是 best stable choice"的判断标准。

**改进建议**：
增加明确的"稳定性判断标准"：
```
Selector Stability Criteria (evaluate in order):
1. ID-based: #unique-id is most stable (but verify ID appears only once in document)
2. Data-attribute: [data-testid="..."] is stable if the attribute is semantic, not auto-generated
3. Semantic class: .news-item (if clearly semantic and not shared)
4. Tag + semantic class: article.card (combines tag semantics with class)
5. Position-based: .item:nth-child(3) is FRAGILE - avoid unless no other option
6. Complex descendant: div > ul > li > span (stable if ancestors are semantic landmarks)
```

---

#### 9.2.3 PAGINATION_ANALYSIS_PROMPT 评估

**专家 A（Playwright 开发者）评语：**

> "分页分析是整个选择器生成流程中最复杂的部分，现有设计已经相当健壮，但仍有实战盲点。"

**问题 1：infinite_scroll 策略的 wait 机制缺失**

提示词识别出 infinite_scroll 策略后，生成的选择器是空的：
```json
{
  "pagination_strategy": "infinite_scroll",
  "next_button_selector": "",
  ...
}
```

但 Playwright 实现 infinite_scroll 需要：
- 滚动位置检测
- 新内容加载检测
- 停止条件（max_pages 或无新内容出现）

**改进建议**：
在提示词中增加 infinite_scroll 的实现指导：
```
For infinite_scroll strategy:
- next_button_selector will be empty (scroll-based, no button)
- You MUST implement content-change detection: compare item count or last visible element before and after scroll
- Add a max_scroll_attempts or max_pages limit to prevent infinite loops
- Use page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)") and wait for new content
- Verify content actually loaded by checking if new items appeared in the DOM
```

**问题 2：多语言 Next 按钮文本检测不够全面**

当前检测模式：
```
NEXT_TEXT_RE = re.compile(r"\b(next|more|load\s*more|下一页|加载更多|更多)\b", re.IGNORECASE)
```

漏掉了常见变体：
- "Load More" (无空格)
- "View More"
- "See More"
- "加载更多内容"
- "下一页"
- "下页"
- "后一页"
- "Next Page"
- 俄语: "Следующая"
- 西班牙语: "Siguiente"
- 日语: "次へ"

**改进建议**：
在提示词中补充更多语言模式，或要求 LLM 主动检测页面上的按钮文本。

**问题 3：分页策略与选择器的矛盾检测缺失**

场景：当 LLM 识别出 pagination_strategy 为 "click_next" 但同时 next_button_selector 为空字符串时，系统没有报错。

**改进建议**：
在输出格式要求中增加一致性检查：
```
Consistency Check (MUST pass before returning):
- If pagination_strategy is "click_next" or "load_more", next_button_selector MUST NOT be empty
- If pagination_strategy is "infinite_scroll", next_button_selector SHOULD be empty
- If pagination_strategy is "none", both next_button_selector and page_number_selectors SHOULD be empty
- Confidence score should reflect the strength of evidence: high confidence requires explicit next semantics visible in HTML
```

---

### 9.3 脚本生成流程评估

#### 9.3.1 CRAWLER_SYSTEM_PROMPT + 生成管线评估

**专家 A（Playwright 开发者）评语：**

> "整体设计非常扎实！骨架增强（Skeleton Enhancement）模式是业界最佳实践之一，但 'pro' 模式的 Review-Revision 流程存在效率问题。"

**问题 1：Review-Revision 流程可能产生过度修订**

当前 pro 模式的管线是：
```
Draft → Review → (if issues) Revision → Final
```

Reviewer 可能提出过于严格的 issue，导致 Revision 产生不必要的修改。例如：
- Review: "class name could be more stable" → Revision: 将 `.news-list > li.item` 改为 `.news-list > li[data-index]`
- 改动后可能引入新问题

**改进建议**：
在 CRAWLER_REVIEW_SYSTEM_PROMPT 中增加"最小改动原则"约束：
```
Revision Policy (add to existing):
- Only request changes that would cause functional failures or critical bugs
- Style preferences and "could be more stable" comments should be marked as "low" severity with "optional" label
- If a selector works and produces correct results, do not change it for theoretical stability improvements
- Prefer adding null-safety and error handling over rewriting working extraction logic
```

**问题 2：Skeleton Enhancement 模式对复杂站点的覆盖不足**

对于复杂站点（如多步登录、验证码处理、IP 限制），骨架脚本可能过于简化。

**改进建议**：
在提示词中增加"复杂场景覆盖"检查表：
```
Complex Scenario Checklist (apply if relevant):
- [ ] Login/Authentication: Are credentials handled securely? Is session persistence implemented?
- [ ] CAPTCHA: Does the plan specify how to handle CAPTCHA? If not, add conservative retry logic
- [ ] Rate Limiting: Is there a polite crawl delay between requests?
- [ ] JavaScript Rendering: Are waits sufficient for SPA content to load?
- [ ] iFrame Content: Does extraction correctly target the right frame?
- [ ] Shadow DOM: Are selectors compatible with shadow DOM traversal?
```

**问题 3：ElementHandle.locator() 误用检测事后处理**

当前管线在生成 draft 后检测 ElementHandle.locator() 问题：
```python
draft_compatibility_issues = _detect_script_compatibility_issues(draft_script)
```

这意味着问题已经被生成了才发现，需要重新生成。

**改进建议**：
在 CRAWLER_SYSTEM_PROMPT 中将这个约束提升为"最高优先级禁止规则"：
```
CRITICAL CONSTRAINTS (violation = immediate rejection):
1. NEVER use ElementHandle.locator() - this API does not exist in Playwright Python sync API
2. NEVER use page.locator() when you have an ElementHandle available
3. NEVER use locator chaining like item.locator(".title").first() when item IS an ElementHandle

Correct patterns:
- page.locator("article.item").first().query_selector(".title") 
- page.query_selector("article.item").query_selector(".title")
```

---

#### 9.3.2 提示词与生成管线整合评估

**专家 B（提示词大师）评语：**

> "提示词分散在多个文件中，缺少统一的版本控制和变更追踪机制。"

**问题 1：提示词分散导致不一致性风险**

当前提示词分布在：
- `llm_client.py` - 4 个核心提示词（CRAWLER_SYSTEM_PROMPT 等）
- `backend/workflows/generation_pipeline.py` - 2 个提示词（CRAWLER_REVIEW_SYSTEM_PROMPT, CRAWLER_REVISION_SYSTEM_PROMPT）
- `prompts/crawler_prompt.py` - 动态生成的用户提示词
- `backend/assist/json_protocol.py` - JSON 修复相关提示词

**潜在冲突示例**：
- `SELECTOR_OPTIMIZATION_PROMPT` 说 "keep XPath as is"
- `crawler_prompt.py` 中的 `_build_selector_contract()` 说 "Do not convert a validated XPath selector to CSS"

两者描述相似但措辞不同，可能导致 LLM 在不同调用上下文中的行为不一致。

**改进建议**：
建立"提示词一致性矩阵"，明确每个提示词的职责边界：
```
| 提示词 | 职责 | 输出格式 | 上下文 |
|--------|------|----------|--------|
| CRAWLER_SYSTEM_PROMPT | 生成完整爬虫脚本 | Python 代码 | generate_with_system |
| CRAWLER_REVIEW_SYSTEM_PROMPT | 审查脚本质量 | JSON review | generate_with_system |
| CRAWLER_REVISION_SYSTEM_PROMPT | 修订脚本 | Python 代码 | generate_with_system |
| FIELD_INFERENCE_PROMPT | 从 HTML 推断字段 | JSON fields | generate |
| SELECTOR_OPTIMIZATION_PROMPT | 优化选择器 | JSON selector | generate |
| PAGINATION_ANALYSIS_PROMPT | 分析分页策略 | JSON pagination | generate |
```

**问题 2：Response Contract 与提示词主体分离**

当前设计将 Response Contract 放在 `assist_services.py` 中作为字符串常量：
```python
FIELD_INFERENCE_RESPONSE_CONTRACT = """Return one JSON object with this shape:
{
  "item_selector": "string",
  "fields": [...],
  ...
}"""
```

而提示词主体在 `llm_client.py` 中。

**改进建议**：
将 Response Contract 直接嵌入提示词，避免两侧更新不同步：
```
FIELD_INFERENCE_PROMPT = """
... main prompt content ...

## Output Format (MANDATORY)
Return a JSON object with this EXACT structure:
{
  "item_selector": "CSS selector matching ONLY repeating list items",
  "fields": [
    {"name": "field_name", "selector": "CSS selector", "type": "text|attr:href|attr:src", "confidence": 0.0-1.0}
  ],
  "confidence": 0.0-1.0,
  "reason": "explanation of extraction logic"
}
"""
```

---

### 9.4 升级优化建议汇总

#### 9.4.1 高优先级优化（影响生成正确性）

| # | 提示词 | 问题 | 优化建议 | 预期效果 |
|---|--------|------|---------|---------|
| 1 | FIELD_INFERENCE_PROMPT | LLM 生成全局作用域选择器 | 增加"干扰项示例"段落，明确排除列表外元素 | 减少误匹配 |
| 2 | FIELD_INFERENCE_PROMPT | HTML 截断丢失信息 | 保留首尾两端，中间用占位符 | 保留分页信息 |
| 3 | CRAWLER_SYSTEM_PROMPT | ElementHandle.locator() 误用 | 提升为最高优先级禁止规则 | 减少生成后检测 |
| 4 | PAGINATION_ANALYSIS_PROMPT | infinite_scroll 实现指导缺失 | 增加滚动检测和停止条件指导 | 提升无限滚动场景可用性 |

#### 9.4.2 中优先级优化（影响稳定性）

| # | 提示词 | 问题 | 优化建议 | 预期效果 |
|---|--------|------|---------|---------|
| 5 | SELECTOR_OPTIMIZATION_PROMPT | 优化安全边界不明确 | 增加 XPath 保留原则、简单化偏好 | 减少兼容性问题 |
| 6 | FIELD_INFERENCE_PROMPT | 图片懒加载支持不足 | 增加 data-src 系列属性优先级 | 提升图片提取准确率 |
| 7 | CRAWLER_REVIEW_SYSTEM_PROMPT | 过度修订风险 | 增加最小改动原则约束 | 减少不必要改动 |
| 8 | PAGINATION_ANALYSIS_PROMPT | 多语言 Next 按钮检测不全 | 扩展正则表达式覆盖更多语言 | 提升国际化站点支持 |

#### 9.4.3 低优先级优化（长期改进）

| # | 提示词 | 问题 | 优化建议 | 预期效果 |
|---|--------|------|---------|---------|
| 9 | 所有 JSON 输出提示词 | Response Contract 分离 | 将格式契约嵌入提示词主体 | 减少版本不一致 |
| 10 | 多个提示词 | 约束分散 | 建立统一的"自检清单"块 | 提升 LLM 遵循度 |
| 11 | CRAWLER_SYSTEM_PROMPT | 复杂场景覆盖不足 | 增加复杂场景检查表 | 提升复杂站点可用性 |
| 12 | 整体架构 | 提示词分散在多处 | 建立提示词一致性矩阵文档 | 便于维护和追踪变更 |

---

### 9.5 设计流程高质高效评估

#### 9.5.1 现有流程的优点

**专家 A（Playwright 开发者）认可的设计：**

1. **Skeleton Enhancement 模式**：基于确定性骨架增强而非从零生成，降低了 LLM 自由度过高导致的控制流漂移风险。

2. **Review-Revision 两阶段管线**：pro 模式的双重验证确保脚本质量，对生产环境爬虫尤为重要。

3. **Sandbox 执行验证**：`run_generated_script_sandbox` 在实际执行环境中验证脚本，发现 import 错误、语法错误、依赖问题。

4. **ElementHandle 检测**：正则表达式检测 `item.locator(` 等常见误用模式，减少运行时错误。

5. **分页策略与选择器验证**：`analyze_pagination` 后的 `validate_actionable_pagination_selector` 将选择器在真实页面上验证。

**专家 B（提示词大师）认可的设计：**

1. **Decision Hierarchy 清晰**：5 级决策层级明确优先级，避免 LLM 在冲突指令中随机选择。

2. **Failure Policy 明确**："never hallucinate"、"never invent" 等明确的失败策略定义了行为边界。

3. **响应格式契约化**：所有 JSON 输出都有明确的 schema 定义和规则说明。

#### 9.5.2 现有流程的不足

**从实战角度的关键瓶颈：**

1. **提示词版本管理缺失**：没有 changelog 或版本标注，当 LLM 输出质量下降时难以定位是提示词问题还是模型问题。

2. **缺乏 A/B 测试机制**：无法比较不同提示词版本的实际效果差异。

3. **失败模式归因困难**：当 `infer_fields` 失败时，无法确定是 HTML 质量问题、提示词歧义还是模型能力不足。

4. **Token 预算无差异化分配**：简单任务（如选择器优化）可能使用与复杂任务相同的 max_tokens，导致浪费或截断。

---

### 9.6 结论

**整体评价**：现有提示词和生成流程的设计处于业界中上水平，骨架增强模式和两阶段管线是亮点。选择器和分页分析的提示词基本可用，但存在若干实战盲点需要填补。

**最优先改进项**：
1. 增强 FIELD_INFERENCE_PROMPT 的干扰项排除能力
2. 将 ElementHandle.locator() 约束提升为最高优先级
3. 完善 infinite_scroll 的实现指导
4. 统一 Response Contract 与提示词主体

---

*专家评估时间：2026-04-29*
*评估版本：llm_client.py 当前版本*
*评估范围：提示词设计、选择器生成流程、脚本生成管线*
