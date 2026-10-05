// Petit composable de fetch : data / loading / error / refresh.
// Sur 401 (token absent ou faux) bascule l'UI en mode saisie de token.
import { ref, onMounted, type Ref } from 'vue'
import api, { setToken } from './api'

export const needsToken = ref(localStorage.getItem('lottery_token') === null && localStorage.getItem('lottery_auth_required') === '1')

export function submitToken(t: string) {
  setToken(t)
  needsToken.value = false
  localStorage.removeItem('lottery_auth_required')
}

export function useFetch<T = any>(path: string, params?: Record<string, any>) {
  const data: Ref<T | null> = ref(null)
  const loading = ref(true)
  const error = ref('')

  async function refresh() {
    loading.value = true
    error.value = ''
    try {
      const res = await api.get(path, { params })
      data.value = res.data.data
    } catch (e: any) {
      if (e.response?.status === 401) {
        localStorage.setItem('lottery_auth_required', '1')
        needsToken.value = true
      }
      error.value = e.response?.data?.error || e.message || 'erreur réseau'
    } finally {
      loading.value = false
    }
  }

  onMounted(refresh)
  return { data, loading, error, refresh }
}
