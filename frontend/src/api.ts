import axios, { AxiosError } from 'axios'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`).replace(/\/$/, '')
export const WS_URL = import.meta.env.VITE_WS_URL || `${API_BASE_URL.replace(/^http/, 'ws')}/ws/dashboard`

export const api = axios.create({ baseURL: API_BASE_URL, timeout: 12000 })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('smarthome_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use((response) => response, (error: AxiosError) => {
  const path = error.config?.url || ''
  if (error.response?.status === 401 && !path.includes('/api/auth/login') && !path.includes('/api/security/recognize')) {
    window.dispatchEvent(new Event('smarthome-auth-expired'))
  }
  return Promise.reject(error)
})

export function apiError(error: unknown): string {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((entry) => entry.msg || 'Dữ liệu không hợp lệ').join('; ')
    if (!error.response) return 'Không kết nối được Backend. Hãy kiểm tra máy chủ tại cổng 8000.'
    if (error.response.status === 401) return 'Phiên đăng nhập hết hạn hoặc thông tin chưa đúng.'
    if (error.response.status === 403) return 'Tài khoản không có quyền thực hiện thao tác này.'
    return `Yêu cầu thất bại (${error.response.status}).`
  }
  return error instanceof Error ? error.message : 'Đã xảy ra lỗi không xác định.'
}

export function imageUrl(path: string | null | undefined): string | null {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

export function formatTime(value: string | null | undefined, includeDate = false): string {
  if (!value) return 'Chưa có dữ liệu'
  // SQLite timestamps from this backend are UTC but may omit the timezone suffix.
  const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('vi-VN', {
    ...(includeDate ? { day: '2-digit', month: '2-digit', year: 'numeric' } : {}),
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(date)
}
