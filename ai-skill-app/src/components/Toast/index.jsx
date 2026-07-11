import { useCallback, useState } from 'react'
import styles from './index.module.scss'
import { ToastContext } from './context'

let toastId = 0

const icons = {
  success: '✓',
  error: '!',
  warning: '!',
  info: 'i'
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((message, type = 'info', duration = 3000) => {
    const id = ++toastId
    setToasts((prev) => [...prev, { id, message, type }])
    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((toast) => toast.id !== id))
      }, duration)
    }
    return id
  }, [])

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  const toast = {
    success: (message) => addToast(message, 'success'),
    error: (message) => addToast(message, 'error', 5000),
    info: (message) => addToast(message, 'info'),
    warning: (message) => addToast(message, 'warning', 4000),
  }

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className={styles.toastContainer}>
        {toasts.map((item) => (
          <div
            key={item.id}
            className={`${styles.toast} ${styles[item.type]}`}
            onClick={() => removeToast(item.id)}
          >
            <span className={styles.icon}>{icons[item.type]}</span>
            <span className={styles.message}>{item.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
