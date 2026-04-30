# Crawler Workflow

`crawler-workflow` 是一个基于 DSL 的浏览器爬虫工作流系统。它将 FastAPI 后端、Playwright 浏览器会话与 React 可视化工作台组合在一起，用于完成工作流编排、有界执行测试，以及 AI 辅助脚本生成。

## 当前范围

- 工作流 DSL 校验与图编辑
- 有界的 `test-node` / `test-subflow` 执行
- Prompt 预览、骨架脚本生成、完整爬虫脚本生成
- 选择器检测、字段推断、分页分析、数据清洗等 AI 辅助动作
- 前端工作台中的脚本与提示词编辑工作区
- 独立的详情页页面采集工具 `page-extractor`（供批处理脚本或手工 CLI 调用）

## 快速开始

### Python 后端

```bash
uv sync
python server.py
```

后端默认地址：`http://127.0.0.1:8000`

### React 工作台

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3101
```

前端默认地址：`http://127.0.0.1:3101`

## 常用命令

```bash
# 后端测试
.venv\Scripts\python.exe -m pytest tests -v

# 详情页 CLI 帮助
page-extractor collect --help

# 前端测试
cd frontend
npm run test

# 前端构建
cd frontend
npm run build
```

## 项目结构

```text
crawler-workflow/
├── server.py                  # 根目录兼容启动入口
├── backend/                   # 后端真实实现
│   ├── api/                   # FastAPI 路由层
│   ├── assist/                # assist 任务编排与 JSON 协议
│   ├── core/                  # settings / logging / api_response
│   ├── extraction/            # DOM 检测、HTML 提取、选择器测试
│   ├── llm/                   # LLM client 实现
│   ├── prompts/               # prompt 共享规则、契约、任务与组装器
│   ├── runtime/               # 浏览器会话、异步桥接、记录输出
│   └── workflow/              # workflow schema、编译、执行、脚本生成
├── page_extractor/            # 独立详情页采集工具与 CLI 运行时
├── frontend/                  # React 工作台
│   └── src/
│       ├── app/               # 应用壳层与布局编排
│       ├── features/          # workflow / assist / results / prompt-workspace
│       ├── services/          # API client
│       └── shared/            # 共享资源
├── docs/                      # 当前有效文档、专项分析与归档文档
└── tests/                     # 后端测试
```

## 文档入口

- [docs/README.md](docs/README.md)
- [docs/documentation-audit.md](docs/documentation-audit.md)
- [docs/product-guide.md](docs/product-guide.md)
- [docs/technical-guide.md](docs/technical-guide.md)
- [docs/engineering-diagnosis-and-optimization-plan.md](docs/engineering-diagnosis-and-optimization-plan.md)
- [docs/optimization-implementation-plan.md](docs/optimization-implementation-plan.md)
- [docs/developer-checklist.md](docs/developer-checklist.md)
- [docs/analysis/guide.md](docs/analysis/guide.md)
- [page_extractor/README.md](page_extractor/README.md)
- [docs/page-extractor-cli-guide.md](docs/page-extractor-cli-guide.md)
- [docs/page-extractor-publish-and-install.md](docs/page-extractor-publish-and-install.md)
- [DESIGN.md](DESIGN.md)

## 备注

- `GET /` 当前返回简单的 API 说明信息，主要的编排界面在 React 工作台中。
- 临时截图、调试输出、一次性规划笔记不应保留在仓库根目录。
