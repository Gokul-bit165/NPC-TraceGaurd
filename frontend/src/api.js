import axios from 'axios'

// Demo role switcher. Real deployments sit behind campus SSO; these headers are not a security boundary.
export const ROLES = {
  admin: { label: 'IT Administrator', name: 'Asha Menon', userId: '' },
  analyst: { label: 'Security Analyst', name: 'Ravi Kumar', userId: '' },
  user: { label: 'Student / Staff', name: 'Nikhil Rao', userId: 'u-nikhil' },
}
export const getRole = () => localStorage.getItem('tg_role') || 'analyst'
export const setRole = (r) => localStorage.setItem('tg_role', r)

const api = axios.create({ baseURL: '/api' })
api.interceptors.request.use((cfg) => {
  const r = getRole()
  cfg.headers['X-Role'] = r
  cfg.headers['X-User'] = ROLES[r].name
  cfg.headers['X-User-Id'] = ROLES[r].userId
  return cfg
})
export const errText = (e) => e?.response?.data?.detail?.message || e?.response?.data?.detail || e.message
export default api
