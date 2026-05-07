# Sea Data Workbench - Local Bridge 操作说明

本文档介绍了 Sea Data Workbench 最新引入的 **Local Bridge（本地桥接）** 混合架构，以及如何启动、配置和使用该模式进行本地化采集与测试。

## 1. 架构简介

以前的架构强制使用云端的 Playwright 无头浏览器执行任务，不利于调试和处理复杂的本地网络/登录态环境。

目前的**混合架构**分为两部分：
- **云端/中枢服务**：FastAPI 后端和 React 前端。它们负责编排、存储以及 AI 分析。
- **本地桥接端 (Local Bridge)**：在你的本地机器上拉起一个基于你本机 Chrome 的 CDP (Chrome DevTools Protocol) 实例，并通过 WebSocket 长连接隧道连接到后端的 Relay 中心。

当你在前端进行“节点测试”或“AI 分析”时，只要选择了本地环境，云端的执行指令就会直接穿透发往你的本机浏览器，实现“云端编排，本地执行”的完美结合。

## 2. 服务启动步骤

为了完整运行整套环境，你需要分别启动**三个**终端会话。

### 终端 1：启动 FastAPI 后端服务
后端负责提供各类 Workflow 及 Assist API，并承载 WebSocket Relay 服务。
```bash
# 在工程根目录下执行
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
> **注意**：默认运行端口必须是 `8000`，这与前端的默认 Proxy 配置一致。

### 终端 2：启动 React 前端工作台
前端提供可视化的工作流编排界面。
```bash
# 进入 frontend 目录
cd frontend
# 启动 Vite 开发服务器（由于需要代理至 8000 端口，这里会启动在 3101 端口）
npm run dev -- --host 127.0.0.1 --port 3101
```

### 终端 3：启动 Local Bridge 本地桥接客户端
该脚本会自动检测你的操作系统并拉起本地 Chrome 浏览器，接着连回后端的 8000 端口。
```bash
# 进入 packages/local-bridge 目录
cd packages/local-bridge

# 安装依赖（如果是初次运行）
npm install

# 启动 Bridge 客户端，需传入你要注册的 Agent ID 和后端的 WebSocket 地址
npx ts-node --esm index.ts test_agent ws://127.0.0.1:8000
```
> **提示**：命令行中的 `test_agent` 是你的设备唯一标识。你可以随意更改，但前端设置中需要填入相同的值。

## 3. 在前端界面的配置与使用

一旦上述三个服务都成功启动并且 Bridge 显示 `✅ Bridge successfully established! Waiting for workflows...`：

1. 打开浏览器访问：[http://127.0.0.1:3101](http://127.0.0.1:3101)
2. 在工作台顶部工具栏中找到 **环境 (Environment)** 切换器。
3. 将执行环境从默认的 `Cloud` 切换为 **`Local CDP`**。
4. 在随后出现的输入框中填写你的 Agent ID，即 **`test_agent`**（要与终端 3 启动时使用的 ID 保持一致）。
5. 此时你可以选中画布中的 `open_page` 节点（并在右侧面板填入你想要测试的网址），然后点击 **“节点测试”** 或使用其他 AI 辅助功能。
6. 你会看到你**本地弹出的那个 Chrome 窗口**自动开始执行网页导航和操作，而执行日志和结果会直接返回到前端的执行控制台中！

## 4. 常见问题排查 (FAQ)

- **Q: 启动 Local Bridge 时提示“Unexpected server response: 404”**
  **A**: 这意味着 FastAPI 后端没有找到 WebSocket 路由，可能是你连接的端口错误（比如连了 Vite 的 3101 端口），请确保桥接脚本连的是 `ws://127.0.0.1:8000`。
- **Q: 点击“节点测试”或“AI 辅助”时控制台报 `ECONNREFUSED`**
  **A**: 这表示 Vite 无法代理到后端 API。请检查终端 1 中的 FastAPI 服务是否成功挂载并运行在 `127.0.0.1:8000` 上。
- **Q: 桥接刚连上，但一执行任务就闪断 (code=1006)？**
  **A**: 这个问题曾经出现过并已被修复。如果你仍遇到，请确保后端代码 (`backend/api/relay.py`) 是最新的，并且 FastAPI 进程已经被重启。
- **Q: 报错 `cannot import name 'from_json' from 'jiter'`**
  **A**: 说明 Python 虚拟环境中的 `jiter` 包发生了损坏。请在根目录执行 `uv pip uninstall jiter` 再执行 `uv pip install jiter`，并**重启 FastAPI 服务**。
