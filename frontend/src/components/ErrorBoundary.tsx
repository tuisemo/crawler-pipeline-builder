import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Result, Button } from 'antd'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[ErrorBoundary] Uncaught error:', error, errorInfo)
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
          <Result
            status="error"
            title="页面出现异常"
            subTitle="应用发生了意外错误，请尝试刷新页面。"
            extra={[
              <Button type="primary" key="reload" onClick={() => window.location.reload()}>
                刷新页面
              </Button>,
              <Button key="retry" onClick={this.handleRetry}>
                重试
              </Button>,
            ]}
          />
        </div>
      )
    }
    return this.props.children
  }
}
