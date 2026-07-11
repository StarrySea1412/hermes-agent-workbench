import React from 'react'
import styles from './ErrorBoundary.module.scss'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className={styles.errorBoundary}>
          <div className={styles.errorContent}>
            <div className={styles.errorIcon}>!</div>
            <h2 className={styles.errorTitle}>页面遇到了一点问题</h2>
            <p className={styles.errorMessage}>
              {this.state.error?.message || '应用发生了意外错误。'}
            </p>
            <button className={styles.retryButton} onClick={this.handleRetry}>
              重试
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
