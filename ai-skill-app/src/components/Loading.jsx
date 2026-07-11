import styles from './Loading.module.scss'

export default function Loading({ text = '加载中...', fullScreen = false }) {
  return (
    <div className={`${styles.loading} ${fullScreen ? styles.fullScreen : ''}`}>
      <div className={styles.spinnerContainer}>
        <div className={styles.spinner} />
        {text ? <span className={styles.text}>{text}</span> : null}
      </div>
    </div>
  )
}
