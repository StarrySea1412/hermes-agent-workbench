import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getCurrentUser } from '../api/auth'
import { clearStoredToken, setLocalModeBypass, useAuthSnapshot } from '../auth/storage'

const AUTH_ERROR_STATUSES = new Set([401, 403])

export function useAuth() {
  const queryClient = useQueryClient()
  const authSnapshot = useAuthSnapshot()
  const shouldAttemptSession = Boolean(authSnapshot.token) || !authSnapshot.skipLocalMode

  const currentUserQuery = useQuery({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
    enabled: shouldAttemptSession,
    retry: false,
    staleTime: 60 * 1000,
  })

  const isAuthError = AUTH_ERROR_STATUSES.has(currentUserQuery.error?.status)
  const hasUnexpectedError = Boolean(currentUserQuery.error) && !isAuthError

  useEffect(() => {
    if (!authSnapshot.token || !isAuthError) {
      return
    }

    clearStoredToken()
    setLocalModeBypass(true)
    queryClient.removeQueries({ queryKey: ['currentUser'] })
  }, [authSnapshot.token, isAuthError, queryClient])

  const isAuthenticated = Boolean(currentUserQuery.data)
  const isLoading = shouldAttemptSession && currentUserQuery.isLoading
  const isLocalMode = Boolean(currentUserQuery.data) && !authSnapshot.token

  const logout = () => {
    clearStoredToken()
    setLocalModeBypass(true)
    queryClient.clear()
  }

  return {
    user: currentUserQuery.data || null,
    isLoading,
    isAuthenticated,
    isLocalMode,
    error: hasUnexpectedError ? currentUserQuery.error : null,
    logout,
  }
}
