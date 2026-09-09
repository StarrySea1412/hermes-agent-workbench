import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { login } from '../api/auth'
import { setLocalModeBypass, setStoredToken } from '../auth/storage'
import styles from './Login.module.scss'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const loginMutation = useMutation({
    mutationFn: () => login(username, password),
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
    loginMutation.mutate()
  }

  return (
    <div className={styles.loginContainer}>
      <div className={styles.loginCard}>
        <div className={styles.logoArea}>
          <span className={styles.logoText}>H</span>
        </div>

        <h1 className={styles.title}>登录 Hermes</h1>
        <p className={styles.subtitle}>继续查看运行记录、工具、技能和执行轨迹。</p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.inputGroup}>
            <label htmlFor="username" className={styles.label}>用户名</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="请输入用户名"
              className={styles.input}
              disabled={loginMutation.isPending}
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
              placeholder="请输入密码"
              className={styles.input}
              disabled={loginMutation.isPending}
              required
            />
          </div>

          {loginMutation.isError ? (
            <div className={styles.error}>
              {loginMutation.error.message || '登录失败，请重试。'}
            </div>
          ) : null}

          <button
            type="submit"
            className={styles.submitBtn}
            disabled={loginMutation.isPending || !username || !password}
          >
            {loginMutation.isPending ? '登录中...' : '登录'}
          </button>

          <p className={styles.registerHint}>
            还没有账号？
            <Link to="/register" className={styles.registerLink}>立即注册</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
