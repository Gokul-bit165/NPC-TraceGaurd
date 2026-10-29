import axios from 'axios'

// Demo role switcher. Real deployments sit behind campus SSO; these headers are not a security boundary.
export const ROLES = {
  admin: { label: 'IT Administrator', name: 'Asha Menon', userId: '' },
  analyst: { label: 'Security Analyst', name: 'Ravi Kumar', userId: '' },
  user: { label: 'Student / Staff', name: 'Nikhil Rao', userId: 'u-nikhil' },
}
export const getRole = () => {
  const r = localStorage.getItem('tg_role')
  return ROLES[r] ? r : 'analyst'
}
export const setRole = (r) => localStorage.setItem('tg_role', r)

// The backend has no login endpoint: identity is the role header above. "Signing in" picks a demo identity
// and checks the API accepts it; this flag only drives the UI, it is not a security boundary.
export const isSignedIn = () => localStorage.getItem('tg_signed_in') === '1'
export const markSignedIn = () => localStorage.setItem('tg_signed_in', '1')
export const signOut = () => localStorage.removeItem('tg_signed_in')
export const homeFor = (role) => (role === 'user' ? '/my-alerts' : '/')

const api = axios.create({ baseURL: '/api' })
api.interceptors.request.use((cfg) => {
  const r = getRole()
  cfg.headers['X-Role'] = r
  cfg.headers['X-User'] = ROLES[r].name
  cfg.headers['X-User-Id'] = ROLES[r].userId
  return cfg
})
export const errText = (e) => {
  const d = e?.response?.data?.detail
  const msg = d?.message || (typeof d === 'string' ? d : null) || e?.message || 'Request failed'
  // A proxy error with no response means the API itself is not reachable.
  if (!e?.response && e?.request) return 'Cannot reach the TraceGuard API. Check that the backend is running on port 8000.'
  return String(msg)
}
export default api
