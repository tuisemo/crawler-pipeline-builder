import { Button } from 'antd'
import {
  DownloadOutlined,
  ChromeOutlined,
  SelectOutlined,
  ThunderboltOutlined,
  CodeOutlined,
  AimOutlined,
  ApiOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { detectExtension, type ExtensionStatus } from '../features/runtime/extensionBridge'
import './extension.css'

const EXTENSION_ZIP_PATH = './extensions/browser-bridge-extension.zip'

export default function ExtensionPage() {
  const navigate = useNavigate()
  const [extensionStatus, setExtensionStatus] = useState<ExtensionStatus | null>(null)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      const status = await detectExtension(1500)
      if (!cancelled) setExtensionStatus(status)
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const isConnected = extensionStatus?.installed && extensionStatus?.ready

  return (
    <div className="extension-page">
      {/* Hero */}
      <div className="extension-page-hero">
        <h1>Browser Bridge 扩展</h1>
        <p>
          安装 Browser Bridge 浏览器扩展，在工作台中直接操控目标网页、智能识别页面结构、
          实时调试 CSS 选择器，让数据采集工作流所见即所得。
        </p>
      </div>

      {/* Connection Status */}
      <div className={`extension-status-bar ${isConnected ? 'connected' : 'disconnected'}`}>
        <span className="status-dot" />
        {extensionStatus === null
          ? '正在检测扩展连接状态…'
          : isConnected
            ? `扩展已连接${extensionStatus.version ? ` (v${extensionStatus.version})` : ''}`
            : '扩展未连接 — 请按照下方步骤安装'}
      </div>

      {/* Download Card */}
      <div className="extension-page-section">
        <h2>下载安装包</h2>
        <div className="extension-download-card">
          <div className="extension-download-info">
            <h3>Browser Bridge Extension</h3>
            <p>适用于 Chrome / Edge / 其他 Chromium 内核浏览器 · Manifest V3</p>
          </div>
          <Button
            type="primary"
            size="large"
            icon={<DownloadOutlined />}
            href={EXTENSION_ZIP_PATH}
            download="browser-bridge-extension.zip"
            style={{ borderRadius: 10, fontWeight: 600, flexShrink: 0 }}
          >
            下载扩展 (.zip)
          </Button>
        </div>
      </div>

      {/* Installation Guide */}
      <div className="extension-page-section">
        <h2>安装步骤</h2>
        <ol className="extension-step-list">
          <li>
            <strong>下载扩展包</strong> — 点击上方「下载扩展」按钮，将压缩包保存到本地。
          </li>
          <li>
            <strong>解压扩展包</strong> — 将下载的文件解压到一个固定目录（例如 <code style={{ fontFamily: 'var(--sd-font-mono)', fontSize: 13, background: 'var(--sd-color-bg-surface)', padding: '2px 6px', borderRadius: 4 }}>~/browser-bridge-extension</code>），安装后请勿删除此目录。
          </li>
          <li>
            <strong>打开扩展管理页</strong> — 在 Chrome 地址栏输入 <code style={{ fontFamily: 'var(--sd-font-mono)', fontSize: 13, background: 'var(--sd-color-bg-surface)', padding: '2px 6px', borderRadius: 4 }}>chrome://extensions</code>，或通过菜单 → 扩展 → 管理扩展进入。
          </li>
          <li>
            <strong>开启开发者模式</strong> — 点击页面右上角「开发者模式」开关将其打开。
          </li>
          <li>
            <strong>加载已解压的扩展</strong> — 点击左上角「加载已解压的扩展程序」，选择刚才解压的目录。扩展列表中出现 <strong>Scraper Flow Studio Bridge</strong> 即表示安装成功。
          </li>
          <li>
            <strong>刷新工作台</strong> — 返回 Scraper Flow Studio 工作台页面并刷新，顶部工具栏应显示「本地扩展已就绪」。
          </li>
        </ol>
      </div>

      {/* Features */}
      <div className="extension-page-section">
        <h2>核心能力</h2>
        <div className="extension-feature-grid">
          <div className="extension-feature-card">
            <div className="feature-icon" style={{ background: 'rgba(6,182,212,0.08)' }}>
              <AimOutlined style={{ color: '#06B6D4' }} />
            </div>
            <h4>AI 智能识别</h4>
            <p>自动检测列表项容器、分页组件和字段选择器，一键生成采集规则。</p>
          </div>
          <div className="extension-feature-card">
            <div className="feature-icon" style={{ background: 'rgba(79,70,229,0.08)' }}>
              <SelectOutlined style={{ color: '#4F46E5' }} />
            </div>
            <h4>选择器实时调试</h4>
            <p>在工作台中输入 CSS 选择器，目标页面即时高亮匹配元素，所见即所得。</p>
          </div>
          <div className="extension-feature-card">
            <div className="feature-icon" style={{ background: 'rgba(22,163,74,0.08)' }}>
              <CodeOutlined style={{ color: '#16A34A' }} />
            </div>
            <h4>HTML 片段提取</h4>
            <p>直接从目标页面提取结构化 HTML 片段，在工作流节点中即时预览数据。</p>
          </div>
          <div className="extension-feature-card">
            <div className="feature-icon" style={{ background: 'rgba(245,158,11,0.08)' }}>
              <ApiOutlined style={{ color: '#F59E0B' }} />
            </div>
            <h4>分页上下文感知</h4>
            <p>自动识别分页导航结构和翻页策略，为多页采集提供完整上下文。</p>
          </div>
        </div>
      </div>

      {/* Architecture Note */}
      <div className="extension-page-section">
        <h2>工作原理</h2>
        <p>
          Browser Bridge 是一个轻量级 Manifest V3 扩展，通过 Content Script 注入到工作台页面中，
          建立 Page ↔ Extension ↔ Target Tab 的双向桥接通道。工作台前端通过
          <code style={{ fontFamily: 'var(--sd-font-mono)', fontSize: 13, background: 'var(--sd-color-bg-surface)', padding: '2px 6px', borderRadius: 4 }}>window.postMessage</code>
          发送 RPC 请求，Content Script 转发至 Background Service Worker，
          再由 Service Worker 在目标标签页执行脚本并返回结果。全程本地运行，不涉及任何外部服务。
        </p>
      </div>

      {/* Actions */}
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <Button
          size="large"
          icon={<ThunderboltOutlined />}
          onClick={() => navigate('/tasks')}
          style={{ borderRadius: 10, fontWeight: 600, marginRight: 12 }}
        >
          进入工作台
        </Button>
        <Button
          size="large"
          icon={<ChromeOutlined />}
          onClick={() => window.open('chrome://extensions', '_blank')}
          style={{ borderRadius: 10 }}
        >
          打开扩展管理
        </Button>
      </div>
    </div>
  )
}
