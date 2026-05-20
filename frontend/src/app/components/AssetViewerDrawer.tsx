import { useState, useEffect, useCallback } from 'react'
import { Drawer, Timeline, Button, Space, Tooltip, Modal, message, Tag, Spin, Typography } from 'antd'
import {
  CopyOutlined,
  DownloadOutlined,
  RollbackOutlined,
  HistoryOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
} from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import type { AssetVersionMeta } from '../../services/taskApi'
import { getAssetHistory, getAssetByVersion, rollbackAsset } from '../../services/taskApi'

const { Text } = Typography

const assetTypeLabel: Record<string, string> = {
  workflow_graph: '工作流图',
  compile_plan: '编译计划',
  list_script: '列表脚本',
  prompt: '提示词',
  detail_batch_config: '批处理配置',
  detail_batch_script: '批处理脚本',
}

function getMonacoLanguage(assetType: string): string {
  if (assetType === 'list_script' || assetType === 'detail_batch_script') return 'python'
  if (assetType === 'workflow_graph' || assetType === 'compile_plan' || assetType === 'detail_batch_config') return 'json'
  if (assetType === 'prompt') return 'markdown'
  return 'plaintext'
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

type AssetViewerDrawerProps = {
  open: boolean
  taskId: number
  assetType: string
  latestVersion: number
  onClose: () => void
  onRollbackSuccess: () => void
}

export function AssetViewerDrawer({
  open,
  taskId,
  assetType,
  latestVersion,
  onClose,
  onRollbackSuccess,
}: AssetViewerDrawerProps) {
  const [history, setHistory] = useState<AssetVersionMeta[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [content, setContent] = useState<string>('')
  const [contentLoading, setContentLoading] = useState(false)
  const [rollbackLoading, setRollbackLoading] = useState(false)
  const activeVersion = selectedVersion ?? latestVersion

  // Load version history when drawer opens
  useEffect(() => {
    if (!open || !assetType) return
    let cancelled = false

    const loadHistory = async () => {
      setHistoryLoading(true)
      try {
        const res = await getAssetHistory(taskId, assetType)
        if (!cancelled) {
          setHistory(res.versions)
        }
      } catch {
        if (!cancelled) {
          message.error('加载历史版本失败')
        }
      } finally {
        if (!cancelled) {
          setHistoryLoading(false)
        }
      }
    }

    void loadHistory()
    return () => {
      cancelled = true
    }
  }, [open, taskId, assetType, latestVersion])

  // Load content when selected version changes
  const loadContent = useCallback(async (version: number) => {
    setContentLoading(true)
    try {
      const res = await getAssetByVersion(taskId, assetType, version)
      let rawContent = res.content ?? ''
      // Auto pretty-print JSON assets
      if (getMonacoLanguage(assetType) === 'json' && rawContent) {
        try {
          rawContent = JSON.stringify(JSON.parse(rawContent), null, 2)
        } catch {
          // not valid JSON, show as-is
        }
      }
      setContent(rawContent)
    } catch {
      message.error(`加载 REV_${String(version).padStart(2, '0')} 内容失败`)
    } finally {
      setContentLoading(false)
    }
  }, [taskId, assetType])

  useEffect(() => {
    if (!open || activeVersion <= 0) return

    void Promise.resolve().then(() => loadContent(activeVersion))
  }, [open, activeVersion, loadContent])

  function handleClose() {
    setSelectedVersion(null)
    onClose()
  }

  function handleCopy() {
    if (!content) return
    navigator.clipboard.writeText(content).then(
      () => message.success('已复制到剪贴板'),
      () => message.error('复制失败，请手动选择复制'),
    )
  }

  function handleDownload() {
    if (!content) return
    const ext = assetType.includes('script') ? 'py' : assetType === 'workflow_graph' ? 'json' : 'txt'
    const filename = `${assetType}_rev${String(activeVersion).padStart(2, '0')}.${ext}`
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  function handleRollback() {
    if (activeVersion === latestVersion) return
    Modal.confirm({
      title: '确认版本回滚',
      content: (
        <div>
          <p>将把 <strong>REV_{String(activeVersion).padStart(2, '0')}</strong> 的内容重新写入为最新版本。</p>
          <p style={{ color: '#999', fontSize: 12 }}>当前最新版本 REV_{String(latestVersion).padStart(2, '0')} 不会被删除，仅新增一条记录。</p>
        </div>
      ),
      okText: '确认回滚',
      cancelText: '取消',
      okButtonProps: { style: { background: '#000', border: 'none' } },
      onOk: async () => {
        setRollbackLoading(true)
        try {
          await rollbackAsset(taskId, assetType, activeVersion)
          message.success(`已成功回滚至 REV_${String(activeVersion).padStart(2, '0')} 内容，新版本已创建`)
          onRollbackSuccess()
          handleClose()
        } catch {
          message.error('回滚失败，请重试')
        } finally {
          setRollbackLoading(false)
        }
      },
    })
  }

  const label = assetTypeLabel[assetType] || assetType
  const language = getMonacoLanguage(assetType)
  const isLatest = activeVersion === latestVersion

  return (
    <Drawer
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <HistoryOutlined style={{ color: '#999' }} />
          <span style={{ fontFamily: 'var(--sd-font-mono)', fontSize: 14, fontWeight: 600 }}>
            {label}
          </span>
          <Tag style={{ margin: 0, fontFamily: 'var(--sd-font-mono)', fontSize: 11, border: 'none', background: '#f0f0f0' }}>
            {assetType.toUpperCase()}
          </Tag>
        </div>
      }
      open={open}
      onClose={handleClose}
      width={960}
      styles={{ body: { padding: 0, display: 'flex', height: '100%', overflow: 'hidden' } }}
    >
      <div style={{ display: 'flex', height: '100%', width: '100%' }}>
        {/* Left: Version Timeline */}
        <div style={{
          width: 220,
          borderRight: '1px solid #f0f0f0',
          padding: '24px 20px',
          overflowY: 'auto',
          flexShrink: 0,
          background: '#fafafa',
        }}>
          <div style={{ fontFamily: 'var(--sd-font-mono)', fontSize: 11, color: '#bbb', letterSpacing: '0.08em', marginBottom: 20 }}>
            历史版本 / HISTORY
          </div>
          {historyLoading ? (
            <div style={{ textAlign: 'center', paddingTop: 40 }}>
              <Spin size="small" />
            </div>
          ) : (
            <Timeline
              items={history.map((v) => ({
                dot: v.version === latestVersion
                  ? <CheckCircleFilled style={{ color: '#000', fontSize: 14 }} />
                  : <ClockCircleOutlined style={{ color: '#ccc', fontSize: 13 }} />,
                children: (
                  <div
                    onClick={() => setSelectedVersion(v.version)}
                    style={{
                      cursor: 'pointer',
                      padding: '8px 12px',
                      borderRadius: 8,
                      background: activeVersion === v.version ? '#000' : 'transparent',
                      transition: 'all 0.15s ease',
                      marginBottom: 4,
                    }}
                  >
                    <div style={{
                      fontFamily: 'var(--sd-font-mono)',
                      fontSize: 13,
                      fontWeight: 600,
                      color: activeVersion === v.version ? '#fff' : '#000',
                    }}>
                      REV_{String(v.version).padStart(2, '0')}
                      {v.version === latestVersion && (
                        <Tag style={{ marginLeft: 6, fontSize: 9, lineHeight: '14px', border: 'none', background: activeVersion === v.version ? 'rgba(255,255,255,0.2)' : '#e8f5e9', color: activeVersion === v.version ? '#fff' : '#16a34a', padding: '0 5px' }}>
                          最新
                        </Tag>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: activeVersion === v.version ? 'rgba(255,255,255,0.6)' : '#bbb', marginTop: 3 }}>
                      {new Date(v.created_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </div>
                    <div style={{ fontSize: 11, color: activeVersion === v.version ? 'rgba(255,255,255,0.5)' : '#ccc', marginTop: 1 }}>
                      {formatBytes(v.content_size)}
                    </div>
                  </div>
                ),
              }))}
            />
          )}
        </div>

        {/* Right: Monaco Editor + Actions */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {/* Action Bar */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 20px',
            borderBottom: '1px solid #f0f0f0',
            background: '#fff',
          }}>
            <Text style={{ fontFamily: 'var(--sd-font-mono)', fontSize: 12, color: '#999' }}>
              预览 REV_{String(activeVersion).padStart(2, '0')} · {language}
            </Text>
            <Space size={8}>
              <Tooltip title="复制代码">
                <Button size="small" icon={<CopyOutlined />} onClick={handleCopy} disabled={contentLoading || !content} />
              </Tooltip>
              <Tooltip title="下载文件">
                <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload} disabled={contentLoading || !content} />
              </Tooltip>
              {!isLatest && (
                <Tooltip title={`回滚至此版本，写入为新的最新版本`}>
                  <Button
                    size="small"
                    icon={<RollbackOutlined />}
                    loading={rollbackLoading}
                    onClick={handleRollback}
                    style={{ borderColor: '#d97706', color: '#d97706' }}
                  >
                    回滚至此版本
                  </Button>
                </Tooltip>
              )}
            </Space>
          </div>

          {/* Editor */}
          <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
            {contentLoading && (
              <div style={{
                position: 'absolute', inset: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                background: 'rgba(255,255,255,0.8)', zIndex: 10,
              }}>
                <Spin tip="加载内容..." />
              </div>
            )}
            <Editor
              height="100%"
              language={language}
              value={content}
              options={{
                readOnly: true,
                minimap: { enabled: false },
                fontSize: 13,
                lineHeight: 22,
                scrollBeyondLastLine: false,
                wordWrap: language === 'markdown' ? 'on' : 'off',
                renderLineHighlight: 'none',
                contextmenu: false,
                folding: true,
                lineNumbers: 'on',
              }}
            />
          </div>
        </div>
      </div>
    </Drawer>
  )
}
