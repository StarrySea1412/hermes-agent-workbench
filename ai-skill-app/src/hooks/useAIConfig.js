import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as aiConfigApi from '../api/aiConfig'

export function useAIConfig() {
  return useQuery({
    queryKey: ['aiConfig'],
    queryFn: () => aiConfigApi.getAIConfig(),
    retry: false,
  })
}

export function useCreateAIConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) => aiConfigApi.createAIConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['aiConfig'] })
    },
  })
}

export function useUpdateAIConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) => aiConfigApi.updateAIConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['aiConfig'] })
    },
  })
}

export function useTestAIConfig() {
  return useMutation({
    mutationFn: () => aiConfigApi.testAIConfig(),
  })
}

export function useFetchAIModels() {
  return useMutation({
    mutationFn: (data) => aiConfigApi.fetchAIModels(data),
  })
}

export function useCcSwitchProviders() {
  return useQuery({
    queryKey: ['ccSwitchProviders'],
    queryFn: async () => {
      try {
        return await aiConfigApi.listCcSwitchProviders()
      } catch (error) {
        return { found: false, path: '', providers: [], error: error.message }
      }
    },
    staleTime: 60000,
  })
}

export function useImportCcSwitchProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (providerId) => aiConfigApi.importCcSwitchProvider(providerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['aiConfig'] })
    },
  })
}

export function useHermesStatus() {
  return useQuery({
    queryKey: ['hermesStatus'],
    queryFn: async () => {
      try {
        return await aiConfigApi.getHermesStatus()
      } catch {
        return { available: false, connected: false, message: 'Hermes 网关当前不可用。' }
      }
    },
    retry: false,
    refetchInterval: 30000,
  })
}

export function useHermesSkills() {
  return useQuery({
    queryKey: ['hermesSkills'],
    queryFn: async () => {
      const result = await aiConfigApi.getHermesSkills()
      return result.skills || []
    },
    retry: false,
  })
}

export function useHermesSkillDetail(skillPath) {
  return useQuery({
    queryKey: ['hermesSkillDetail', skillPath],
    queryFn: () => aiConfigApi.getHermesSkillDetail(skillPath),
    enabled: Boolean(skillPath),
    retry: false,
  })
}

export function useHermesMonitor({ includeChat = false, refetchInterval = 30000 } = {}) {
  return useQuery({
    queryKey: ['hermesMonitor', includeChat],
    queryFn: async () => {
      try {
        return await aiConfigApi.getHermesMonitor({ includeChat })
      } catch (error) {
        return {
          connected: false,
          tcp_connected: false,
          models_connected: false,
          chat_connected: false,
          message: 'Hermes 监控当前不可用。',
          error: error.message,
          checks: [],
        }
      }
    },
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    refetchInterval,
  })
}
