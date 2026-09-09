import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { register } from '../api/auth'
import { setLocalModeBypass, setStoredToken } from '../auth/storage'
import styles from './Login.module.scss'

export default function Register() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const registerMutation = useMutation({
    mutationFn: () => register(username, password),
    onSuccess: async (data) => {
      const token = data?.access_token || data?.token
      if (token) {
        setStoredToken(token)
        setLocalModeBypass(false)
        await queryClient.invalidateQueries({ queryKey: ['currentUser'] })
        navigate('/')
      }
    },
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    if (password !== confirmPassword) return
    registerMutation.mutate()
  }

  const passwordMismatch = Boolean(confirmPassword && password !== confirmPassword)

  return (
    <div className={styles.loginContainer}>
      <div className={styles.loginCard}>
        <div className={styles.logoArea}>
          <span className={styles.logoText}>H</span>
        </div>

        <h1 className={styles.title}>创建账号</h1>
        <p className={styles.subtitle}>注册后即可在你的个人工作台中保存运行记录、配置和智能体模板。</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.inputGroup}>
            <label htmlFor="username" className={styles.label}>用户名</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="至少 3 个字符"
              className={styles.input}
              disabled={registerMutation.isPending}
              minLength={3}
              required
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="password" className={styles.label}>密码</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="至少 6 个字符"
              className={styles.input}
              disabled={registerMutation.isPending}
              minLength={6}
              required
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="confirmPassword" className={styles.label}>确认密码</label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="请再次输入密码"
              className={`${styles.input} ${passwordMismatch ? styles.inputError : ''}`}
              disabled={registerMutation.isPending}
              required
            />
            {passwordMismatch ? <span className={styles.fieldError}>两次输入的密码不一致。</span> : null}
          </div>

          {registerMutation.isError ? (
            <div className={styles.error}>
              {registerMutation.error.message || '注册失败，请重试。'}
            </div>
          ) : null}

          <button
            type="submit"
            className={styles.submitBtn}
            disabled={registerMutation.isPending || !username || !password || passwordMismatch}
          >
            {registerMutation.isPending ? '创建中...' : '创建账号'}
          </button>

          <p className={styles.registerHint}>
            已经有账号了？
            <Link to="/login" className={styles.registerLink}>去登录</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
