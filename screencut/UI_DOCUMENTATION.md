# Crawler Workflow 前端界面截图文档

> 本文档用于记录 Crawler Workflow 可视化爬虫工作流设计器的前端界面截图及功能说明，供 AI 设计评估与重构参考。

**应用地址**: http://127.0.0.1:3101  
**技术栈**: React + React Flow (画布) + Ant Design (UI) + Monaco Editor (DSL编辑器)  
**视口设置**: 1920x1080 (14寸笔记本屏幕模拟)

---

## 核心功能模块

Crawler Workflow 是一个 **浏览器驱动的可视化爬虫编排工具**，其核心交互界面分为以下五大区域：

| 模块 | 描述 | 关键文件 |
|------|------|----------|
| **命令栏 (Toolbar)** | 顶部操作区，包含模式切换、DSL操作、Prompt预览、执行操作 | `App.tsx` |
| **节点面板 (Node Palette)** | 左侧可折叠面板，拖放式节点类型库 | `NodePalette.tsx` |
| **画布 (Canvas)** | 中央 React Flow 工作区，拖拽连接编排节点图 | `WorkflowCanvas.tsx` |
| **属性面板 (Property Panel)** | 右侧可折叠面板，配置选中节点的参数 | `PropertyPanel.tsx` |
| **底栏 Dock** | 底部抽屉，包含执行结果和 DSL 编辑器两个标签页 | `ResultsPanel.tsx`, `DslEditorPanel.tsx` |

### 节点类型 (8种)

根据左侧节点面板，功能分为：

1. **open_page** - 打开页面 (入口节点)
2. **click_element** - 点击元素
3. **select_list** - 列表选择/抓取
4. **extract_field** - 提取字段
5. **input_text** - 输入文本
6. **wait** - 等待/延迟
7. **paginate** - 分页/翻页
8. **condition** - 条件分支
9. **end** - 终止节点

### 两种生成模式

- **Lite (轻量模式)** - 快速生成简单爬虫脚本
- **Pro (专业模式)** - 生成完整可配置的爬虫脚本

---

## 截图清单与说明

### 01_overview.png

**描述**: 应用初始加载后的完整工作区视图（2560x1440大屏）

**可见内容**:
- 顶部深色命令栏 (Toolbar)，包含 "Lite" 和 "Pro" 模式切换单选框
- 左侧节点面板已打开，显示节点类型列表（蓝色圆形按钮 "添加"）
- 中央为浅色画布区域，初始带有两个节点（open_page 和 extract_field），通过箭头连接
- 右侧面板为 Property Panel（已打开状态），显示 "基础信息" 和 "节点配置" 两个折叠区块
- 底部命令栏按钮组：校验 DSL、预览 Prompt、优化布局、生成骨架、生成爬虫脚本

**文件路径**: `screencut/01_overview.png`

---

### 02_annotated.png

**描述**: 主界面带元素编号标注的截图

**标注元素**:
- `[3]` 节点库按钮 (layout icon)
- `[4]` 属性按钮 (appstore icon)
- `[5]` 结果按钮 (bars icon)
- `[6]` save DSL
- `[7]` check-circle 校验 DSL
- `[8]` file-search 预览 Prompt
- `[9]` appstore 编排计划
- `[10]` node-index 优化布局
- `[11]` code 生成骨架
- `[12]` rocket 生成爬虫脚本
- `[13-20]` 节点面板的添加按钮 (8种节点类型)
- `[21-24]` 画布缩放控制 (Zoom In, Zoom Out, Fit View, Toggle Interactivity)
- `[25]` 打开结果与 DSL 工作区
- `[26]` 收起属性面板
- `[27]` 基础信息折叠区块
- `[31]` 节点配置折叠区块

**文件路径**: `screencut/02_annotated.png`

---

### 03_full_overview.png

**描述**: 2560x1440 全屏下的完整界面截图（更宽的工作区）

**可见内容**:
- 左侧节点面板展示更多节点类型的添加按钮
- 画布区域更大，节点分布更宽松
- 右侧属性面板显示 URL 输入框 "https://example.com/page"
- 底部 "打开结果与 DSL 工作区" 按钮可见

**文件路径**: `screencut/03_full_overview.png`

---

### 04_results_tab.png / 05_bottom_dock_open.png

**描述**: 点击工具栏 "bars 结果" 按钮后，底部 Dock 展开的界面

**Dock 展开后的可见内容**:
- Drawer 从屏幕底部向上展开，高度约 84vh
- 顶部有关闭按钮 `[33]`
- 两个标签页：`[34]` "bars 执行结果"（默认选中）和 `[35]` "save DSL 编辑器"
- 执行结果标签显示：节点数、边数、字段数、分页状态等统计信息

**文件路径**: `screencut/04_results_tab.png`, `screencut/05_bottom_dock_open.png`

---

### 06_annotated_dock.png

**描述**: 底部 Dock 展开后的带标注截图

**标注元素**:
- `[33]` Close 按钮（关闭 Dock）
- `[34]` tab "bars 执行结果"（当前选中）
- `[35]` tab "save DSL 编辑器"（未选中）

**文件路径**: `screencut/06_annotated_dock.png`

---

### 07_dsl_editor.png

**描述**: 点击 "DSL 编辑器" 标签后的界面

**可见内容**:
- 底部 Dock 切换到 DSL 编辑器标签
- Monaco Editor 显示 JSON 格式的 DSL 内容（画布图结构的序列化表示）
- DSL 内容包含 nodes（节点数组，包含 id、type、position、data）和 edges（边数组）
- 编辑器为深色主题（Dock Slate #0F172A），文字为浅蓝色 (#DBEAFE)
- 当前 DSL 显示 2 个节点（open_page 和 extract_field）及其连接关系

**文件路径**: `screencut/07_dsl_editor.png`

---

### 08_after_add_node.png

**描述**: 从节点面板添加一个新节点后的画布状态

**可见内容**:
- 新增了第三个节点，类型为 select_list
- 节点以卡片形式展示在画布上，通过 React Flow 渲染
- 节点之间通过箭头连接表示数据流向
- 新节点出现在右侧区域，Property Panel 自动打开

**文件路径**: `screencut/08_after_add_node.png`

---

### 09_property_panel.png

**描述**: 右侧属性面板（Property Panel）的详细截图

**可见内容**:
- 面板标题显示 "配置 - xxx"（选中的节点 ID）
- 顶部有 "收起" 按钮用于折叠面板
- **基础信息折叠区**：
  - 节点类型下拉框 (combobox)
  - 节点 ID 输入框
  - 节点名称输入框
- **节点配置折叠区**：
  - URL 输入框 "https://example.com/page"
- 底部有 "删除节点" 操作

**文件路径**: `screencut/09_property_panel.png`

---

### 10_annotated_full.png

**描述**: 主界面带完整标注的截图

**主要标注**:
- `[3]` 节点库 - 切换左侧节点面板显示/隐藏
- `[4]` 属性 - 切换右侧属性面板显示/隐藏
- `[5]` 结果 - 打开底部结果 Dock
- `[6-12]` 工具栏操作按钮组
- `[13-20]` 节点面板中的 8 个添加按钮
- `[21-24]` 画布缩放控制
- `[25]` 打开结果与 DSL 工作区（底部 Dock 快捷按钮）

**文件路径**: `screencut/10_annotated_full.png`

---

### 11_node_library.png

**描述**: 左侧节点面板（Node Palette）展开时的截图

**可见内容**:
- 面板标题 "节点面板" 带有蓝色标签 "8 种"（表示 8 种节点类型）
- 面板内列出所有可添加的节点类型，每种节点旁边有 "添加" 按钮
- 节点类型列表：
  1. open_page - 打开页面（带蓝色 entry 标记）
  2. click_element - 点击元素
  3. select_list - 列表选择
  4. extract_field - 提取字段
  5. input_text - 输入文本
  6. wait - 等待
  7. paginate - 分页
  8. condition - 条件分支

**文件路径**: `screencut/11_node_library.png`

---

### 12_full_with_panels.png

**描述**: 同时打开节点面板和属性面板的完整工作区截图

**可见内容**:
- 三栏布局：左侧节点面板 + 中央画布 + 右侧属性面板
- Toolbar 顶部的 Lite/Pro 模式切换
- 画布上有多个节点（初始的 open_page 和 extract_field，加上新增的节点）
- 节点之间通过箭头连接形成工作流
- 底部命令栏按钮全部可见

**文件路径**: `screencut/12_full_with_panels.png`

---

## 设计风格总结

根据 DESIGN.md 的视觉规范，当前 UI 实现了以下设计原则：

### 色彩应用

| 用途 | 使用的颜色 |
|------|-----------|
| 主应用背景 | Harbor Mist (#F3F7FB) |
| 面板/卡片表面 | Ice Surface (#FFFFFF) |
| 命令栏/工具栏背景 | 深色 Slate (#0F172A) |
| 主操作按钮 | Command Blue (#2563EB) |
| 节点类型标记 | 蓝色系、靛蓝色系 |
| 代码/DSL 编辑器背景 | Dock Slate (#0F172A) 深色主题 |

### 布局结构

- **五区设计**: 顶部命令栏 + 左侧节点库 + 中央画布 + 右侧属性面板 + 底部结果 Dock
- **面板可折叠**: 左右面板可以通过按钮收起/展开
- **底栏为 Drawer**: 结果与 DSL 工作区从底部抽屉展开

### 交互模式

- 点击节点面板的 "添加" 按钮在画布上创建节点
- 点击画布上的节点打开属性面板进行配置
- DSL 编辑器提供 JSON 序列化的工作流视图
- 生成脚本后结果显示在底部执行结果标签中

---

## 待优化项（基于截图分析）

1. **节点面板** - 当前仅有 "添加" 按钮，建议支持拖拽到画布
2. **属性面板** - 配置字段较多时需要滚动，建议增加分组折叠
3. **底部 Dock** - 84vh 高度在小屏幕上可能遮挡画布，建议增加记忆功能
4. **DSL 编辑器** - Monaco Editor 在隐藏后重新显示时可能存在布局计算问题
5. **画布节点** - 当前节点较简略，建议增加状态图标（运行中、已完成、错误）

---

*文档生成时间: 2026-05-09*  
*截图设备: 模拟 14 寸笔记本 (1920x1080) + 大屏 (2560x1440)*
