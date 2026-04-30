# Page Extractor Publish And Install Guide

## 目标

本文档说明如何在当前工程中安装、验证并为后续发布 `page-extractor` CLI 做准备。

它关注：

- 本仓库内安装
- 本地 CLI 验证
- Playwright 依赖初始化
- 未来单独发布时应遵守的约束

## 当前状态

当前 `page_extractor` 已经是仓库根目录下的独立运行时包，并通过：

- [pyproject.toml](/D:/WY-DATASETS/sea-data/pyproject.toml)

声明了 CLI：

- `page-extractor`

这意味着在安装当前仓库后，用户可以直接使用：

```bash
page-extractor collect ...
```

## 仓库内安装方式

### 方式 1：使用 `uv`

```bash
uv sync
```

适用场景：

- 当前仓库开发
- 本地测试
- 与现有 `crawler-workflow` 一起使用

### 方式 2：使用 `pip editable install`

```bash
pip install -e .
```

适用场景：

- 希望把 `page-extractor` 暴露到当前 Python 环境
- 手工验证 console script 是否正确安装

## 验证 CLI 是否已安装

安装完成后，可以先看帮助：

```bash
page-extractor --help
```

再看子命令帮助：

```bash
page-extractor collect --help
```

如果暂时没有 console script，也可以用模块方式验证：

```bash
python -m page_extractor.cli --help
python -m page_extractor.cli collect --help
```

## Playwright 浏览器依赖

`page-extractor` 的页面加载与 PDF 功能依赖 Playwright 浏览器。

第一次使用建议执行：

```bash
playwright install chromium
```

如果你已经在当前项目环境中完成过 Playwright 初始化，通常不需要重复执行。

## 最小功能验收

安装后至少应该验证下面 3 件事：

1. 命令可执行
   - `page-extractor collect --help`

2. 可以处理合法 URL
   - 产出 `summary.json`
   - 产出 `content.md`

3. 非法 URL 会直接失败
   - stdout JSON `status=failed`
   - `error_code=invalid_url`

## 与批处理脚本的集成方式

当前推荐的上游调用方式有两种：

### 方式 A：直接 CLI 名称

```bash
page-extractor collect --url ... --task-id ... --output-root ...
```

### 方式 B：命令前缀调用

```bash
python -m page_extractor.cli collect --url ... --task-id ... --output-root ...
```

对于 `Generate Detail Batch Runner`，建议：

- 在可安装环境里默认使用 `page-extractor`
- 在本地开发/CI/测试环境里允许 `command_prefix = ["python", "-m", "page_extractor.cli"]`

## 发布前建议检查项

如果后续要把 `page_extractor` 作为独立 CLI 对外发布，建议先检查：

1. 入口脚本名称是否稳定
   - `page-extractor`

2. CLI stdout JSON contract 是否稳定

3. `summary.json` / `metadata.json` / `logs/collect.log` 的路径契约是否稳定

4. 依赖是否齐全
   - `requests`
   - `playwright`
   - `beautifulsoup4`
   - `lxml`
   - `cssselect`
   - `trafilatura`

5. 是否有独立 README 和 usage 示例

6. 批处理脚本是否只通过 CLI 调用，不依赖内部 import

## 未来独立发布建议

当前它仍然与主仓库共用一个 `pyproject.toml`。如果未来要完全独立发布，建议：

1. 把 `page_extractor/` 单独抽成独立仓库或独立 Python package
2. 提供独立 `pyproject.toml`
3. 提供独立版本号和 changelog
4. 提供独立 smoke fixtures
5. 保持与主平台的 CLI contract 向后兼容

但在当前阶段，不需要为了发布而立刻拆仓库。先保持：

- 代码独立目录
- CLI 独立入口
- 调用统一走 CLI contract

就已经满足“工程上独立、可发布”的目标。

## 相关文档

- [page_extractor/README.md](/D:/WY-DATASETS/sea-data/page_extractor/README.md)
- [docs/page-extractor-cli-guide.md](/D:/WY-DATASETS/sea-data/docs/page-extractor-cli-guide.md)
- [docs/superpowers/specs/2026-04-30-detail-extractor-cli-contract-spec.md](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-extractor-cli-contract-spec.md)
