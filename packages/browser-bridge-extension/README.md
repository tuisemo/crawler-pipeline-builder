# Browser Bridge Extension

`browser-bridge-extension` 是工作台使用的 Chromium 扩展包，负责在真实标签页内执行选择器测试、高亮、列表自动检测、HTML 片段提取与分页上下文提取。

## 设计原则

- 扩展源码、构建脚本、打包脚本全部放在当前目录内。
- 构建扩展不再依赖 backend 抽取脚本。
- 工作台页面通过 content script 中转与扩展通信，不依赖固定 extension ID。
- 产物分为两类：
  - `release/unpacked`：用于 Chrome / Edge 的“加载已解压的扩展程序”
  - `release/browser-bridge-extension.zip`：用于 Chrome Web Store / Edge Add-ons 上传

## 环境要求

- Node.js 20+
- npm 10+
- Windows 下默认使用 PowerShell 打包 zip
- macOS / Linux 下默认使用系统 `zip` 命令打包

## 安装依赖

```bash
npm install
```

## 稳定扩展 ID

扩展 ID 由公钥决定。为避免每次重新打包后 ID 变化，当前包会在构建前执行：

```bash
npm run prepare:key
```

行为如下：

- 若 `keys/browser-bridge-extension.pem` 已存在，则复用该私钥
- 若不存在，则自动生成新的本地私钥
- 自动把对应公钥写入 `manifest.json` 的 `key` 字段

注意：

- `keys/browser-bridge-extension.pem` 不入库
- `keys/browser-bridge-extension.pem.template` 只作为占位说明
- 如果要在不同机器上保持同一个扩展 ID，必须安全分发并复用同一份私钥

## 构建命令

### 仅编译 dist

```bash
npm run build
```

### 生成解压版扩展

```bash
npm run build:unpacked
```

产物目录：

```text
release/
└── unpacked/
    ├── manifest.json
    └── dist/
```

### 生成商店上传 zip 包

```bash
npm run build:zip
```

产物文件：

```text
release/browser-bridge-extension.zip
```

## 在 Chrome / Edge 中加载

1. 打开 `chrome://extensions/` 或 `edge://extensions/`
2. 开启“开发者模式”
3. 点击“加载已解压的扩展程序”
4. 选择 `packages/browser-bridge-extension/release/unpacked`

加载成功后，应看到 `Browser Bridge for Crawler`。

加载或升级扩展后，请刷新工作台页面，让 content script 重新注入。

## 如何得到“可安装”的浏览器扩展

对 Chromium 系浏览器，需要区分两种“安装”方式：

### 1. 本地开发 / 内部调试

使用 `unpacked` 目录加载，这是最稳定的本地方式：

```bash
npm run build:unpacked
```

### 2. 商店或托管分发

使用 zip 上传到商店：

```bash
npm run build:zip
```

说明：

- `zip` 适合 **Chrome Web Store / Edge Add-ons** 上传
- `zip` 不是 Chromium 本地“直接双击安装”格式
- 如果需要真正的离线安装包，下一步应增加 **签名后的 `.crx` 构建流程**

## 日常发布建议

1. `npm install`
2. `npm run build:zip`
3. 检查 `release/unpacked` 是否可正常加载
4. 将 `release/browser-bridge-extension.zip` 用于商店上传或发布归档
