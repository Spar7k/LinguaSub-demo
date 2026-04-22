import { Component, type ErrorInfo, type ReactNode } from 'react'

type AppErrorBoundaryProps = {
  children: ReactNode
}

type AppErrorBoundaryState = {
  hasError: boolean
  errorMessage: string | null
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = {
    hasError: false,
    errorMessage: null,
  }

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error.message || 'LinguaSub startup failed unexpectedly.',
    }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('LinguaSub render crashed during startup.', error, errorInfo)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <div className="startup-shell">
        <section className="startup-panel">
          <span className="startup-badge">LinguaSub</span>
          <h1>启动失败，但不是空白页</h1>
          <p>
            LinguaSub 在启动主界面时遇到异常。你可以重新加载应用继续尝试；如果问题持续，请把控制台错误或日志发给开发者。
          </p>

          <div className="error-banner" role="alert">
            <strong>启动异常</strong>
            <p>{this.state.errorMessage ?? 'LinguaSub startup failed unexpectedly.'}</p>
          </div>

          <div className="startup-actions">
            <button type="button" className="button button--primary" onClick={this.handleReload}>
              重新加载应用
            </button>
          </div>
        </section>
      </div>
    )
  }
}
