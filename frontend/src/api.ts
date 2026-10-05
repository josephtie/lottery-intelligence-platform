import axios from 'axios'
import { useTagsViewStore } from './stores/tagsView'

const api = axios.create({ baseURL: '/api' })

// Token d'auth si défini côté backend (LOTTERY_API_TOKEN)
const token = localStorage.getItem('lottery_token')
if (token) api.defaults.headers.common['Authorization'] = `Bearer ${token}`

export default api
export function setToken(t: string) {
  localStorage.setItem('lottery_token', t)
  api.defaults.headers.common['Authorization'] = `Bearer ${t}`
}

// Déconnexion: retire le token ET réinitialise les onglets visités
// (les vues affichées revenaient sinon en keep-alive après re-login).
export function logout() {
  localStorage.removeItem('lottery_token')
  delete api.defaults.headers.common['Authorization']
  useTagsViewStore().reset()
}
