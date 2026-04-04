import { Component, type ErrorInfo, type ReactNode } from 'react'

type MessagesV3ErrorBoundaryProps = {
  children: ReactNode
  onRenderError?: (error: Error, info: ErrorInfo) => void
}

type MessagesV3ErrorBoundaryState = {
  hasError: boolean
  errorMessage: string
}

export class MessagesV3ErrorBoundary extends Component<
  MessagesV3ErrorBoundaryProps,
  MessagesV3ErrorBoundaryState
> {
  override state: MessagesV3ErrorBoundaryState = {
    hasError: false,
    errorMessage: '',
  }

  static getDerivedStateFromError(error: Error): MessagesV3ErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error.message || 'Failed to render V3 conversation.',
    }
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onRenderError?.(error, info)
  }

  override render() {
    if (this.state.hasError) {
      return (
        <div role="status" data-testid="messages-v3-render-error">
          {this.state.errorMessage}
        </div>
      )
    }
    return this.props.children
  }
}
