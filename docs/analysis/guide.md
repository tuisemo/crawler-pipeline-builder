# Crawler Workflow 平台操作使用说明手册

## 1. 文档目的

本文档面向 `crawler-workflow` 平台的使用者，帮助你从“日常数据采集脚本设计”的角度理解前端节点面板中的 8 种节点：

1. `open_page`
2. `select_list`
3. `loop`
4. `extract_field`
5. `condition`
6. `paginate`
7. `emit_record`
8. `end`

文档重点不是解释节点名字，而是回答以下问题：

- 这个节点在采集流程里到底扮演什么角色
- 它适合什么场景，不适合什么场景
- 配置项该怎么填
- 和其他节点通常怎么组合
- 在真实的商品列表、资讯列表、目录型网站采集中如何落地

本文同时结合了前端属性面板和当前后端执行器的真实实现语义，因此它既是产品操作手册，也是当前版本能力边界说明。

---

## 2. 平台整体心智模型

### 2.1 这不是“单条命令式爬虫”

`crawler-workflow` 的核心思路不是让你一次性写完整段 Python 代码，而是让你把采集任务拆成若干可视化步骤，再由平台去：

- 校验工作流结构
- 预览 Prompt
- 生成采集脚本骨架或完整脚本
- 在受控浏览器环境中做节点级 / 子流程级测试

### 2.2 8 种节点对应采集脚本里的 8 类职责

如果把传统采集脚本翻译成工作流，这 8 个节点大致对应下面的脚本职责：

| 节点 | 在传统脚本中的对应动作 |
|------|------------------------|
| `open_page` | `page.goto(url)`，进入入口页 |
| `select_list` | 找到列表项容器，例如 `.product-card` |
| `loop` | `for item in items:`，逐条处理 |
| `extract_field` | 从当前项中提取标题、链接、图片等字段 |
| `condition` | `if/else` 条件判断、过滤、分流 |
| `paginate` | 下一页 / 加载更多 / 无限滚动 |
| `emit_record` | 将当前记录输出到结果集合 |
| `end` | 结束流程或某条路径 |

### 2.3 当前平台最适合的任务类型

当前平台最适合以下类型的数据采集任务：

- 商品列表抓取
- 资讯/文章目录抓取
- 企业名录列表抓取
- 带分页的目录型站点采集
- “先列表、后抽字段、再输出”的结构化采集

当前版本不应把它当成：

- 强交互、多页面深链跳转编排平台
- 复杂登录态业务流程自动化平台
- 任意 Python 控制流的图形化替代品

---

## 3. 开始使用前，你需要知道的几个共性配置

### 3.1 所有节点都有“显示名称”

建议把显示名称写成业务语义，而不是只保留系统默认值。

例如：

- `打开分类页`
- `定位商品卡片`
- `抽取商品摘要字段`
- `检查是否为目标品类`
- `进入下一页`

这样在画布变大时会明显更容易排查问题。

### 3.2 属性面板里的 “AI 回填策略”

当前面板支持两种 AI 回填策略：

- `仅当前节点`
- `当前 + 关联节点`

这主要影响你点击“AI 推断字段”“AI 分析分页”“自动检测列表”等辅助动作后，AI 返回的结果会只修改当前节点，还是顺带更新相关节点。

建议：

- 你已经手工调得比较细时，用 `仅当前节点`
- 你还在快速搭骨架时，用 `当前 + 关联节点`

### 3.3 当前版本很强调“有界执行”

多个节点都有类似下面的限制项：

- `max_items`
- `max_pages`
- `max_steps`

这些不是多余配置，而是平台为了避免测试阶段失控而刻意设计的安全边界。

建议在调试阶段先把这些值设小：

- `max_items = 3~10`
- `max_pages = 1~3`
- `max_steps = 20~50`

等流程稳定后，再提高。

---

## 4. 8 种节点逐一说明

## 4.1 `open_page`

### 4.1.1 功能定位

`open_page` 是工作流入口节点，作用是让浏览器打开目标页面。

它解决的是“从哪里开始采”的问题。

如果没有它，后续节点就没有页面上下文：

- `select_list` 不知道要在哪个页面找列表
- `paginate` 不知道要翻哪一页
- `extract_field` 也无从谈起

### 4.1.2 适用场景

- 商品列表页入口
- 分类页入口
- 新闻栏目页入口
- 搜索结果页入口
- 某个固定 URL 的目录页

### 4.1.3 主要配置项

#### `url`

目标入口地址，必须填写。

示例：

```text
https://www.eworldship.com/app/product_1772.html
https://quotes.toscrape.com/
https://example.com/products?page=1
```

#### `max_pages`

入口节点允许的最大页数边界。

虽然真正翻页通常由 `paginate` 节点负责，但这里仍然作为整体边界之一存在。

#### `max_steps`

整个测试执行过程中允许的最大步骤数，主要用于防止错误流程导致的死循环或过长链路。

### 4.1.4 在脚本中的作用

相当于：

```python
page.goto(url)
```

### 4.1.5 常见搭配

- `open_page -> select_list`
- `open_page -> select_list -> extract_field`
- `open_page -> select_list -> paginate`

### 4.1.6 使用建议

- URL 一定使用完整地址，建议以 `http://` 或 `https://` 开头
- 调试阶段不要把 `max_steps` 设太大
- 如果一个工作流里出现多个 `open_page`，通常说明你的流程设计过于分叉，建议先收敛

### 4.1.7 示例

场景：抓取某个分类页第一页商品摘要

```json
{
  "id": "open-page-1",
  "type": "open_page",
  "data": {
    "label": "打开行业商品页",
    "url": "https://www.eworldship.com/app/product_1772.html",
    "max_pages": 2,
    "max_steps": 20
  }
}
```

---

## 4.2 `select_list`

### 4.2.1 功能定位

`select_list` 用于定位页面中“重复出现的列表项容器”。

它解决的是“这一页上，哪些 DOM 块代表一条条记录”的问题。

这是列表型采集最关键的节点之一。很多用户会急着先配字段，但如果列表容器选错，后面提的字段都会乱。

### 4.2.2 适用场景

- 商品卡片列表
- 文章列表
- 企业名录列表
- 招聘岗位列表
- 搜索结果列表

### 4.2.3 主要配置项

#### `item_selector`

列表项选择器，必须填写。

它应该选中“每一条记录的外层容器”，而不是整个列表父容器。

正确思路：

- 选中每个商品卡片
- 选中每篇文章摘要块
- 选中每条企业记录

不推荐直接选：

- 整个列表总容器
- 页面主内容容器
- 过于细碎的内部字段元素

#### `max_items`

本节点在测试时最多关注多少条列表项。

### 4.2.4 AI 辅助能力

当前平台在 `select_list` 节点上提供三类辅助动作：

#### `自动检测列表`

系统尝试自动识别页面中的列表项结构。

适合：

- 首次搭建流程
- 页面结构较规整
- 不确定哪个 class 才是列表项

#### `优化选择器`

当你已经写了一个选择器，但怀疑它不稳定或太脆弱时，可以让 AI 帮你优化。

#### `测试选择器`

立刻验证当前选择器能匹配到多少元素。

这是最实用的功能之一，建议养成频繁点测试的习惯。

### 4.2.5 在脚本中的作用

相当于：

```python
items = page.query_selector_all(item_selector)
```

### 4.2.6 常见搭配

- `open_page -> select_list -> extract_field`
- `open_page -> select_list -> loop -> extract_field`
- `open_page -> select_list -> paginate`

### 4.2.7 使用建议

- 尽量选列表项外层稳定容器
- 不要一上来就选内部标题 `a` 或图片 `img`
- 如果翻页后匹配数量突然异常，优先怀疑 `item_selector` 太脆弱
- 测试时先看匹配数量，再看样例结构是否像“完整记录”

### 4.2.8 示例

场景：定位商品卡片

```json
{
  "id": "select-list-1",
  "type": "select_list",
  "data": {
    "label": "定位商品卡片",
    "item_selector": ".product-item",
    "max_items": 10
  }
}
```

---

## 4.3 `loop`

### 4.3.1 功能定位

`loop` 用于显式表达“逐条处理上游列表项”。

它解决的是“这个流程接下来要按每个列表项分别执行”的问题。

在概念上，它相当于脚本里的：

```python
for item in items:
    ...
```

### 4.3.2 适用场景

- 你希望明确表达“对每条记录分别处理”
- 后面要接 `condition` 过滤某些条目
- 后面要分支决定某些条目是否输出
- 希望对单条失败设置容错策略

### 4.3.3 当前实现上的真实语义

根据当前后端执行器实现，`loop` 节点主要做的是：

- 读取上游 `select_list` 已经检测到的记录数
- 计算循环上限 `loop_bound`
- 记录当前循环容错策略
- 为后续节点准备循环上下文

也就是说，它更偏“循环上下文控制器”，而不是前端看起来那种会自动展开复杂子流程的高级循环引擎。

### 4.3.4 主要配置项

#### `max_items`

循环最多处理多少条。

这会和平台整体的 `max_items` 共同决定最终处理条数。

#### `on_error`

单条失败时如何处理：

- `skip`：跳过当前项，继续处理下一项
- `stop`：遇到错误立即停止

### 4.3.5 在脚本中的作用

相当于：

```python
for item in items[:max_items]:
    try:
        ...
    except Exception:
        if on_error == "stop":
            raise
        else:
            continue
```

### 4.3.6 常见搭配

- `select_list -> loop -> extract_field -> emit_record`
- `select_list -> loop -> extract_field -> condition -> emit_record`

### 4.3.7 什么时候必须加 `loop`

严格来说，在简单列表页抽字段时，不一定非要加 `loop` 才能跑通；但从产品设计和可读性角度，以下情况推荐显式加入：

- 你要对每条记录做条件筛选
- 你要强调单条容错
- 你要把“列表识别”和“逐条处理”在画布上区分开

### 4.3.8 示例

场景：只取前 20 条商品，单条失败跳过

```json
{
  "id": "loop-1",
  "type": "loop",
  "data": {
    "label": "逐条处理商品",
    "max_items": 20,
    "on_error": "skip"
  }
}
```

---

## 4.4 `extract_field`

### 4.4.1 功能定位

`extract_field` 用于定义“每条记录要抽哪些字段、如何抽、抽成什么格式”。

它解决的是“最终结构化结果长什么样”的问题。

这是整个工作流里最像“采集 schema 定义”的节点。

### 4.4.2 适用场景

- 抽标题、详情链接、封面图
- 抽价格、品牌、规格、发布日期
- 抽标签、作者、来源、摘要

### 4.4.3 主要配置项

#### `fields`

字段列表，每个字段通常包括：

- `name`：字段名
- `selector`：字段相对于当前列表项的选择器
- `type`：抽取方式

#### `html_fragment`

AI 推断字段时保存的 HTML 片段，上层通常无需手工填写。

### 4.4.4 支持的抽取类型

当前前端面板提供以下常见类型：

- `text`
- `attr:href`
- `attr:src`
- `attr:href:abs`
- `html`
- `all(text)`
- `all(@href)`

结合当前 `selector_tester.py` 的实际实现，建议这样理解：

#### `text`

提取文本内容。

适合：

- 标题
- 品牌
- 摘要
- 类目名

#### `attr:href`

提取链接地址原值。

适合：

- 详情页链接

#### `attr:href:abs`

提取链接并转换成绝对地址。

适合：

- 页面使用相对路径时的详情链接

#### `attr:src`

提取图片地址原值。

适合：

- 封面图
- 缩略图

#### `html`

提取 HTML 片段。

适合：

- 复杂说明块
- 后续准备做更细二次处理

#### `all(text)`

提取多个文本值，返回数组。

适合：

- 标签列表
- 多个属性项

#### `all(@href)`

提取多个链接值，返回数组。

适合：

- 一条记录内部包含多个下载地址、多个附件链接

### 4.4.5 AI 辅助能力

#### `AI 推断字段`

基于 HTML 片段推断常见字段。

适合快速搭建初版字段结构，但不要盲信，必须人工复核选择器和字段名。

#### `测试`

测试当前字段选择器是否能在当前上下文中抽到值。

### 4.4.6 在脚本中的作用

相当于：

```python
record = {
    "title": item.query_selector("a.title").inner_text().strip(),
    "detail_url": urljoin(page.url, item.query_selector("a.title").get_attribute("href")),
    "cover": item.query_selector("img").get_attribute("src"),
}
```

### 4.4.8 使用建议

- 字段名尽量使用稳定、业务清晰的英文或统一命名
- 一个字段对应一个明确目标，不要把多个意思塞到一个字段里
- 选择器从当前列表项出发，而不是从整页出发
- 同名字段不要重复，否则结果会被覆盖

### 4.4.9 商品采集典型示例

场景：采集商品标题 + 详情 URL + 封面图

```json
{
  "id": "extract-field-1",
  "type": "extract_field",
  "data": {
    "label": "抽取商品摘要字段",
    "fields": [
      {
        "name": "title",
        "selector": "a.title",
        "type": "text"
      },
      {
        "name": "detail_url",
        "selector": "a.title",
        "type": "attr:href:abs"
      },
      {
        "name": "cover",
        "selector": "img",
        "type": "attr:src"
      }
    ]
  }
}
```

---

## 4.5 `condition`

### 4.5.1 功能定位

`condition` 用于对当前上下文做条件判断，并根据结果把流程分到不同分支。

它解决的是“哪些记录要继续处理、哪些要跳过或走另一条路径”的问题。

### 4.5.2 适用场景

- 只保留标题包含某关键词的记录
- 只保留价格大于某阈值的记录
- 某个字段不存在时走兜底分支
- 对不同类别记录分流处理

### 4.5.3 主要配置项

#### `condition`

条件表达式。

#### `expression_mode`

当前前端提供：

- `simple`
- `advanced`

但根据当前后端实现，真正稳定可用的是 `simple` 风格的白名单表达式。`advanced` 在现阶段更像预留模式，不应假设其有完整高级表达式能力。

#### 出边分支映射

你可以给 `condition` 节点的出边标记：

- `true`
- `false`
- `default`

这会影响后续到底走哪条边。

### 4.5.4 非常重要：当前表达式的真实写法

当前后端执行器实际按“操作符在前”的格式解析，而不是自然语言格式。

建议按下面形式书写：

```text
exists title
not_exists cover
contains title 仪器
not_contains category 二手
equals brand ACME
not_equals status 下架
gt price 100
lt price 50
gte score 4
lte count 1000
```

请特别注意：

- 当前 UI 占位文案更像“title 包含 仪器”
- 但当前执行器真实更接近“contains title 仪器”

手册以当前执行器实现为准。

### 4.5.5 可用操作符

当前后端实现支持：

- `exists`
- `not_exists`
- `contains`
- `not_contains`
- `equals`
- `not_equals`
- `gt`
- `lt`
- `gte`
- `lte`

### 4.5.6 在脚本中的作用

相当于：

```python
if "仪器" in record["title"]:
    ...
else:
    ...
```

或者：

```python
if record["price"] > 100:
    ...
```

### 4.5.7 常见搭配

- `extract_field -> condition -> emit_record`
- `extract_field -> condition -> end`
- `loop -> extract_field -> condition -> emit_record`

### 4.5.8 使用建议

- 先确保字段已经抽出来，再写条件
- 调试条件前，先跑字段抽取测试
- 分支多时务必给边设置清晰标签
- 没有明确分支时，可以留一条 `default` 作兜底

### 4.5.9 示例

场景：只保留标题里含“仪器”的商品

```json
{
  "id": "condition-1",
  "type": "condition",
  "data": {
    "label": "筛选目标品类",
    "condition": "contains title 仪器",
    "expression_mode": "simple"
  }
}
```

---

## 4.6 `paginate`

### 4.6.1 功能定位

`paginate` 用于表达“当前列表抓完后，如何进入下一页继续采”。

它解决的是“如何跨页拿到完整列表”的问题。

### 4.6.2 适用场景

- 有“下一页”按钮
- 有“加载更多”按钮
- 无限滚动列表
- 单页采集时，也可以显式设为 `none`

### 4.6.3 主要配置项

#### `pagination_selector`

分页控件选择器。

例如：

- `a.next`
- `.pagination .next`
- `button.load-more`

#### `pagination_strategy`

当前前端支持：

- `click_next`
- `infinite_scroll`
- `load_more`
- `none`

#### `max_pages`

最多翻多少页。

### 4.6.4 当前实现上的真实语义

根据当前后端 handler，实现上：

- 平台会检查分页选择器是否存在
- 在测试阶段重点是“能不能识别到这个分页控件”
- 不是所有分页策略都已经完全展开成成熟执行逻辑

而在脚本骨架生成侧：

- `click_next` 是当前最明确的主路径
- `load_more` / `infinite_scroll` 更偏可扩展方向

因此建议：

- 如果是标准翻页链接，优先使用 `click_next`
- `load_more` / `infinite_scroll` 适合先做设计表达和提示词生成
- 真正上线前要重点验证生成脚本是否符合站点实际行为

### 4.6.5 AI 辅助能力

#### `AI 分析分页`

基于当前 HTML 片段分析更适合的分页策略和分页选择器。

#### `测试选择器`

快速确认当前分页控件是否能被找到。

### 4.6.6 在脚本中的作用

相当于：

```python
next_button = page.query_selector(pagination_selector)
if next_button:
    next_button.click()
```

### 4.6.7 常见搭配

- `select_list -> extract_field -> paginate`
- `select_list -> loop -> extract_field -> emit_record -> paginate`

### 4.6.8 使用建议

- 不确定分页控件时先点测试
- 如果站点其实只有一页，策略设 `none`
- `max_pages` 在调试期先设小
- 分页后仍然抽不到数据，优先回头检查 `select_list`

### 4.6.9 示例

场景：点击“下一页”抓取更多商品

```json
{
  "id": "paginate-1",
  "type": "paginate",
  "data": {
    "label": "进入下一页",
    "pagination_selector": "a.next",
    "pagination_strategy": "click_next",
    "max_pages": 5
  }
}
```

---

## 4.7 `emit_record`

### 4.7.1 功能定位

`emit_record` 用于把当前已经抽取好的记录正式输出到结果集合中。

它解决的是“哪些数据算最终产出”的问题。

在概念上，它相当于：

```python
results.append(record)
```

### 4.7.2 适用场景

- 抽完字段后准备输出
- 条件判断通过后才输出
- 某条分支只负责过滤，不负责输出，则另一条分支接 `emit_record`

### 4.7.3 当前实现上的真实语义

当前 handler 会从上下文中读取 `extracted_records`，然后输出受 `max_items` 约束的记录。

所以它更像“确认输出”节点，而不是复杂的数据写库节点。

### 4.7.4 主要配置项

当前没有复杂表单配置，重点在于它在流程中的位置。

### 4.7.5 常见搭配

- `extract_field -> emit_record -> end`
- `extract_field -> condition -> emit_record`
- `loop -> extract_field -> emit_record -> paginate`

### 4.7.6 使用建议

- 如果你的目标是“只生成结构化结果”，通常应把它放在字段抽取之后
- 如果还有筛选逻辑，建议放在 `condition` 之后
- `emit_record` 后面最好接 `end`，让路径更清晰

### 4.7.7 示例

场景：抽取成功后输出记录

```json
{
  "id": "emit-record-1",
  "type": "emit_record",
  "data": {
    "label": "输出商品记录"
  }
}
```

---

## 4.8 `end`

### 4.8.1 功能定位

`end` 用于显式标记一条流程路径已经结束。

它解决的是“到这里就停止，不再继续调度后续节点”的问题。

### 4.8.2 适用场景

- 某条分支执行完成后显式终止
- `emit_record` 后明确结束
- 条件不满足时直接终止

### 4.8.3 当前实现上的真实语义

后端 handler 会设置：

```python
ctx.state["ended"] = True
```

这意味着后续不会再继续排队执行新的节点。

### 4.8.4 在脚本中的作用

相当于：

```python
return
```

或者在局部流程里相当于：

```python
break
```

### 4.8.5 常见搭配

- `emit_record -> end`
- `condition(false) -> end`

### 4.8.6 使用建议

- 建议每条完整业务路径都有明确终止点
- 如果图越来越复杂，`end` 节点会明显提升可读性

### 4.8.7 示例

```json
{
  "id": "end-1",
  "type": "end",
  "data": {
    "label": "结束当前流程"
  }
}
```

---

## 5. 节点组合的典型工作流模板

## 5.1 模板一：最常见的商品列表抓取

适合：

- 只抓列表页摘要信息
- 不进入详情页
- 重点采标题、链接、图片、价格等

### 推荐流程

```text
open_page
  -> select_list
  -> extract_field
  -> emit_record
  -> paginate
  -> end
```

### 说明

- `open_page` 打开入口页
- `select_list` 找到每条商品卡片
- `extract_field` 抽出标题/链接/图片等
- `emit_record` 输出结果
- `paginate` 负责继续翻页
- `end` 负责显式终止

### 案例

目标：抓取某分类页全部商品的：

- 商品标题
- 商品详情 URL
- 商品封面图

对应字段设计：

```json
[
  { "name": "title", "selector": "a.title", "type": "text" },
  { "name": "detail_url", "selector": "a.title", "type": "attr:href:abs" },
  { "name": "cover", "selector": "img", "type": "attr:src" }
]
```

---

## 5.2 模板二：先筛选，再输出

适合：

- 只保留目标关键词商品
- 只保留价格在某区间内的记录
- 只输出满足条件的记录

### 推荐流程

```text
open_page
  -> select_list
  -> loop
  -> extract_field
  -> condition
      -> true  -> emit_record -> end
      -> false -> end
```

### 说明

- `loop` 明确逐条处理
- `condition` 判断当前记录是否符合标准
- `true` 分支输出
- `false` 分支直接结束，不输出

### 案例

目标：只保留标题包含“仪器”的商品

```text
condition = contains title 仪器
```

---

## 5.3 模板三：分页验证优先的流程

适合：

- 站点分页复杂
- 你想先证明“翻页逻辑成立”，再细化字段

### 推荐流程

```text
open_page
  -> select_list
  -> paginate
  -> end
```

### 说明

先不急着抽字段，先把：

- 列表选择器
- 分页选择器
- 分页策略

三件事验证清楚。这个思路对陌生站点尤其有用。

---

## 6. 以 eworldship 商品页为例的配置思路

目标页面：

```text
https://www.eworldship.com/app/product_1772.html
```

目标字段：

- 商品标题
- 商品详情 URL
- 商品封面图

### 推荐设计步骤

#### 第一步：打开页面

节点：

- `open_page`

配置：

- `url = https://www.eworldship.com/app/product_1772.html`
- `max_pages = 3`
- `max_steps = 30`

#### 第二步：定位每条商品

节点：

- `select_list`

做法：

- 先用“自动检测列表”
- 再手工验证 `item_selector`
- 使用“测试选择器”确认匹配数

#### 第三步：抽取字段

节点：

- `extract_field`

字段建议：

```json
[
  { "name": "title", "selector": "a", "type": "text" },
  { "name": "detail_url", "selector": "a", "type": "attr:href:abs" },
  { "name": "cover", "selector": "img", "type": "attr:src" }
]
```

注意：

- 真正字段选择器需要以实际列表项 DOM 为准
- 不要照搬示例，必须点“测试”

#### 第四步：输出记录

节点：

- `emit_record`

#### 第五步：配置分页

节点：

- `paginate`

做法：

- 先用 `AI 分析分页`
- 再手动确认 `pagination_selector`
- `pagination_strategy` 优先考虑 `click_next`
- 调试期 `max_pages` 先设 2~3

#### 第六步：结束

节点：

- `end`

---

## 7. 常见错误与排查建议

## 7.1 `select_list` 选错层级

### 现象

- 匹配数很大
- 每条样例看起来不是一条完整记录
- 字段抽取结果混乱

### 处理建议

- 把选择器向内或向外调整到真正单条卡片容器
- 多用“测试选择器”

## 7.2 `extract_field` 直接从整页路径写选择器

### 现象

- 每条记录抽出的值都一样

### 原因

字段选择器应该相对于当前项，而不是相对于整页。

## 7.3 `condition` 写成自然语言但不生效

### 现象

- 明明看起来像中文条件，结果总是走错分支

### 原因

当前执行器更接近“操作符在前”的表达式格式。

### 建议

写成：

```text
contains title 仪器
gt price 100
exists title
```

不要直接写：

```text
title 包含 仪器
price 大于 100
```

## 7.4 只配了 `paginate`，却没抓到数据

### 原因

分页本身不负责字段抽取，它只是负责继续推进页面。

### 建议

确保在分页前已经有：

- `select_list`
- `extract_field`
- `emit_record`

## 7.5 忘了加 `end`

### 现象

- 图看起来能跑，但路径边界不清晰

### 建议

在主要输出路径后加 `end`，可读性和执行边界都会更清楚。

---

## 8. 给用户的实操建议

如果你是第一次使用这个平台，推荐按下面节奏操作：

1. 先只做 `open_page + select_list`
   先证明你真的找到了正确列表项。
2. 再补 `extract_field`
   只先配 1~3 个关键字段。
3. 再补 `emit_record`
   先让结果能出来。
4. 最后再补 `paginate`
   分页永远是后置验证项，不建议一上来就做。
5. 如果要筛选，再加 `condition`
   不要在字段还没稳定时先写条件。
6. 如果要增强语义，再加 `loop`
   尤其适合逐条处理、容错和分支。

---

## 9. 总结：8 种节点在产品中的职责分工

最后用一句话总结这 8 个节点：

- `open_page`：决定从哪里开始
- `select_list`：决定一条记录长什么样
- `loop`：决定是否逐条处理以及如何容错
- `extract_field`：决定最终采什么字段
- `condition`：决定哪些记录留下、哪些分流
- `paginate`：决定如何把整站或多页采全
- `emit_record`：决定哪些结果正式输出
- `end`：决定流程在哪里结束

如果你把这 8 个角色理解清楚，平台就不只是“拖节点”，而是把原本写在脚本里的采集逻辑拆成了可验证、可解释、可逐步完善的工作流。
