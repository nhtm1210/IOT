import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'
import type { LoginResponse, User } from './types'

interface AuthValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    function expireSession() { localStorage.removeItem('smarthome_token'); setUser(null) }
    window.addEventListener('smarthome-auth-expired', expireSession)
    return () => window.removeEventListener('smarthome-auth-expired', expireSession)
  }, [])

  useEffect(() => {
    if (!localStorage.getItem('smarthome_token')) {
      setLoading(false)
      return
    }
    api.get<User>('/api/auth/me')
      .then(({ data }) => setUser(data))
      .catch(() => localStorage.removeItem('smarthome_token'))
      .finally(() => setLoading(false))
  }, [])

  async function login(username: string, password: string) {
    const { data } = await api.post<LoginResponse>('/api/auth/login', { username: username.trim(), password })
    localStorage.setItem('smarthome_token', data.access_token)
    setUser(data.user)
  }

  function logout() {
    localStorage.removeItem('smarthome_token')
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthProvider is missing')
  return value
}
