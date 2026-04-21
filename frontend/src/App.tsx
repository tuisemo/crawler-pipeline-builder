import { useEffect, useState } from 'react'
import './App.css'

type BackendStatus = 'checking' | 'online' | 'offline'
type ResultTone = 'idle' | 'success' | 'error'

const fallbackUrl = 'http://localhost:8000'

const starterGraph = {
  nodes: [
    {
      id: 'open-page-1',
      type: 'open_page',
      data: { url: 'https://quotes.toscrape.com/' },
    },
    {
      id: 'select-list-1',
      type: 'select_list',
      data: { item_selector: '.quote' },
    },
    {
      id: 'extract-field-1',
      type: 'extract_field',
      data: { fields: [{ name: 'text', selector: '.text', type: 'text' }] },
    },
  ],
  edges: [
    { id: 'edge-open-select', source: 'open-page-1', target: 'select-list-1' },
    { id: 'edge-select-extract', source: 'select-list-1', target: 'extract-field-1' },
  ],
}

const paletteItems = [
  { type: 'open_page', label: 'Open page', detail: 'Set target URL' },
  { type: 'select_list', label: 'Select list', detail: 'Choose item selector' },
  { type: 'extract_field', label: 'Extract field', detail: 'Map output fields' },
]

function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('checking')
  const [backendMessage, setBackendMessage] = useState('Checking legacy backend at localhost:8000...')
  const [resultTone, setResultTone] = useState<ResultTone>('idle')
  const [resultMessage, setResultMessage] = useState(
    'Select an action from the toolbar to show validation, prompt preview, node test, or subflow output here.',
  )

  useEffect(() => {
    const controller = new AbortController()

    fetch('/legacy-health', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Backend returned HTTP ${response.status}`)
        }
        setBackendStatus('online')
        setBackendMessage('Legacy fallback backend is reachable on port 8000.')
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        setBackendStatus('offline')
        setBackendMessage(
          'Legacy backend is not reachable. The workbench shell stays available, and the fallback link remains visible.',
        )
      })

    return () => controller.abort()
  }, [])

  function showShellResult(action: string) {
    if (backendStatus === 'offline') {
      setResultTone('error')
      setResultMessage(`${action} cannot reach the backend. Keep authoring locally or open the legacy UI directly.`)
      return
    }

    setResultTone('success')
    setResultMessage(`${action} is available in the shell. Backend integration is handled by the next React milestone.`)
  }

  return (
    <main className="workbench-shell" aria-label="Sea Data React Workbench">
      <header className="toolbar" aria-label="Workbench toolbar">
        <div>
          <span className="eyebrow">Sea Data Workbench</span>
          <h1>Workflow Designer</h1>
        </div>
        <nav className="toolbar-actions" aria-label="Workbench actions">
          <button type="button" onClick={() => showShellResult('Validate DSL')}>
            Validate DSL
          </button>
          <button type="button" onClick={() => showShellResult('Preview Prompt')}>
            Preview Prompt
          </button>
          <button type="button" onClick={() => showShellResult('Run Node Test')}>
            Run Node Test
          </button>
          <a className="fallback-link" href={fallbackUrl} target="_blank" rel="noreferrer">
            Open legacy UI
          </a>
        </nav>
      </header>

      <section className={`backend-banner ${backendStatus}`} aria-live="polite">
        <strong>Backend status:</strong> {backendMessage}
      </section>

      <div className="workspace-grid">
        <aside className="panel node-palette" aria-label="Node palette">
          <div className="panel-heading">
            <span>Node Palette</span>
            <small>MVP list extraction</small>
          </div>
          <div className="palette-list">
            {paletteItems.map((item) => (
              <button key={item.type} type="button" className="palette-card">
                <span>{item.label}</span>
                <small>{item.detail}</small>
              </button>
            ))}
          </div>
          <p className="scope-note">
            Detail-page scraping and complex nested loops are intentionally not required for this MVP shell.
          </p>
        </aside>

        <section className="panel canvas-region" aria-label="Workflow canvas region">
          <div className="panel-heading">
            <span>Canvas</span>
            <small>Visual graph placeholder</small>
          </div>
          <div className="canvas-surface">
            {starterGraph.nodes.map((node, index) => (
              <article key={node.id} className="workflow-node">
                <span className="node-index">{index + 1}</span>
                <div>
                  <strong>{node.type}</strong>
                  <code>{node.id}</code>
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="panel properties-panel" aria-label="Property panel">
          <div className="panel-heading">
            <span>Property Panel</span>
            <small>Selected node</small>
          </div>
          <label>
            Node type
            <input value="open_page" readOnly />
          </label>
          <label>
            Target URL
            <input value="https://quotes.toscrape.com/" readOnly />
          </label>
          <label>
            Item selector
            <input value=".quote" readOnly />
          </label>
        </aside>

        <section className="panel dsl-editor" aria-label="DSL editor region">
          <div className="panel-heading">
            <span>DSL Editor</span>
            <small>Canonical graph JSON</small>
          </div>
          <textarea aria-label="Workflow DSL JSON" value={JSON.stringify(starterGraph, null, 2)} readOnly />
        </section>

        <section className="panel results-area" aria-label="Bottom result area">
          <div className="panel-heading">
            <span>Results</span>
            <small>Validation and execution feedback</small>
          </div>
          <div className={`result-placeholder ${resultTone}`} aria-live="polite">
            {resultMessage}
          </div>
        </section>
      </div>
    </main>
  )
}

export default App
