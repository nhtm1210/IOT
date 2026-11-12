import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import { LiveProvider } from './LiveContext'
import { ToastProvider } from './ToastContext'
import { Layout } from './components/Layout'
const LoginPage = lazy(() => import('./pages/LoginPage').then((module) => ({ default: module.LoginPage })))
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((module) => ({ default: module.DashboardPage })))
const DevicesPage = lazy(() => import('./pages/DevicesPage').then((module) => ({ default: module.DevicesPage })))
const AutomationPage = lazy(() => import('./pages/AutomationPage').then((module) => ({ default: module.AutomationPage })))
const SecurityPage = lazy(() => import('./pages/SecurityPage').then((module) => ({ default: module.SecurityPage })))
const HistoryPage = lazy(() => import('./pages/HistoryPage').then((module) => ({ default: module.HistoryPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((module) => ({ default: module.SettingsPage })))
const UsersPage = lazy(() => import('./pages/UsersPage').then((module) => ({ default: module.UsersPage })))

function ProtectedRoutes() {
  const { user, loading } = useAuth()
  if (loading) return <div className="boot-screen"><div className="brand-mark">S</div><p>Đang kiểm tra phiên đăng nhập...</p></div>
  return user ? <LiveProvider><Layout /></LiveProvider> : <Navigate to="/login" replace />
}

function LoginRoute() {
  const { user, loading } = useAuth()
  if (loading) return <div className="boot-screen">Đang tải...</div>
  return user ? <Navigate to="/dashboard" replace /> : <LoginPage />
}

function AdminRoute() {
  const { user } = useAuth()
  return user?.role === 'ADMIN' ? <UsersPage /> : <Navigate to="/dashboard" replace />
}

export default function App() {
  return <ToastProvider><AuthProvider><BrowserRouter><Suspense fallback={<div className="boot-screen">Đang tải giao diện...</div>}><Routes>
    <Route path="/login" element={<LoginRoute />} />
    <Route element={<ProtectedRoutes />}>
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/devices" element={<DevicesPage />} />
      <Route path="/automation" element={<AutomationPage />} />
      <Route path="/security" element={<SecurityPage />} />
      <Route path="/history" element={<HistoryPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/users" element={<AdminRoute />} />
    </Route>
    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes></Suspense></BrowserRouter></AuthProvider></ToastProvider>
}
