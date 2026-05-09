# Crawler Workflow - 快速启动指南

本文档包含在本地开发或使用 **Crawler Workflow** 时，启动后端服务、前端工作台，以及配置浏览器扩展直连系统的完整步骤。

---

## 1. 启动后端服务 (FastAPI)

后端服务负责提供工作流 API 与纯计算型 LLM 辅助接口。工作台阶段不再通过后端中继浏览器控制。

1. **打开终端** 并进入项目根目录：
   ```bash
   cd d:\WY-DATASETS\sea-data
   ```

2. **激活虚拟环境** (如果使用 `uv`)：
   ```bash
   .venv\Scripts\activate
   ```

3. **启动 FastAPI 服务**：
   ```bash
   uv run server.py
   ```
   *服务将默认在 `http://127.0.0.1:8000` 启动。*

---

## 2. 启动前端工作台 (React + Vite)

前端工作台提供了可视化的 DSL 编排界面、实时执行结果查看和扩展状态感知功能。

1. **进入前端目录**：
   ```bash
   cd d:\WY-DATASETS\sea-data\frontend
   ```

2. **启动 Vite 开发服务器**：
   ```bash
   npm run dev -- --host 127.0.0.1 --port 3101
   ```
   *访问地址: `http://127.0.0.1:3101`。*

---

## 3. 安装与配置 Chrome 扩展 (Browser Bridge)

扩展桥接程序允许工作台直接控制当前活动标签页来进行真实的网页测试、元素高亮和数据提取。

### 3.1 编译扩展程序

1. 进入扩展目录：
   ```bash
   cd d:\WY-DATASETS\sea-data\packages\browser-bridge-extension
   ```
2. 安装依赖并生成解压版扩展：
   ```bash
   npm install
   npm run build:unpacked
   ```
   > 首次构建时会自动生成本地私钥并写入 `manifest.key`，以稳定扩展 ID。
3. 如需生成商店上传包：
   ```bash
   npm run build:zip
   ```

### 3.2 在 Chrome 中加载扩展

1. 打开 Chrome 扩展页面 `chrome://extensions/`。
2. 开启 **“开发者模式”**。
3. 点击 **“加载已解压的扩展程序”**，选择 `d:\WY-DATASETS\sea-data\packages\browser-bridge-extension\release\unpacked` 文件夹。
4. 加载成功后，您将看到 **"Browser Bridge for Crawler"** 扩展。
5. 重新刷新工作台页面，使扩展的 content script 注入到当前工作台。

> `release/browser-bridge-extension.zip` 用于 Chrome Web Store / Edge Add-ons 上传；如需 Chromium 可直接分发安装的离线包，还需额外引入 `.crx` 签名流程。

### 3.3 加载后验证

1. 固定并点击扩展图标打开弹窗。
2. 弹窗显示 `已就绪（本地扩展直连）` 即代表扩展已可用。
3. 保持目标网页为当前活动标签页，再回到工作台进行选择器测试与分页分析。

---

## 4. 在工作台中使用扩展直连

1. 打开工作台界面。
2. 顶部状态标签显示 **“已就绪（本地扩展加速中）”** 后，即可使用辅助能力。
3. 选择器测试、HTML 提取和分页分析都会直接作用于当前活动标签页。
