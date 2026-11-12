import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Activity, Bell, Camera, ChartNoAxesCombined, ChevronLeft, CircleUserRound, Cpu, House, LogOut, Menu, Settings2, Shield, SlidersHorizontal, Users, Wifi, WifiOff, X } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useLive } from '../LiveContext'
import { formatTime } from '../api'

const links = [
  { to: '/dashboard', label: 'Tổng quan', icon: House },
  { to: '/devices', label: 'Thiết bị', icon: Cpu },
  { to: '/automation', label: 'Tự động hóa', icon: SlidersHorizontal },
  { to: '/security', label: 'AI & An ninh', icon: Shield },
  { to: '/history', label: 'Lịch sử', icon: ChartNoAxesCombined },
  { to: '/settings', label: 'Cài đặt', icon: Settings2 },
]

export function Layout() {
  const { user, logout } = useAuth()
  const { snapshot, socketStatus, apiOnline, alerts, lastUpdated } = useLive()
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  function signOut() { logout(); navigate('/login') }

  return <div className="app-shell">
    {menuOpen ? <button className="mobile-scrim" aria-label="Đóng menu" onClick={() => setMenuOpen(false)} /> : null}
    <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><House size={22} strokeWidth={2.2} /></div><div><strong>SMARTHOME<span>.</span></strong><small>IoT CONTROL CENTER</small></div><button className="sidebar-close" aria-label="Đóng menu" onClick={() => setMenuOpen(false)}><X size={19} /></button></div>
      <div className="nav-label">KHÔNG GIAN</div>
      <nav className="main-nav" aria-label="Điều hướng chính">
        {links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Icon size={19} strokeWidth={1.8} /><span>{label}</span><ChevronLeft size={14} className="nav-chevron" /></NavLink>)}
        {user?.role === 'ADMIN' ? <NavLink to="/users" onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Users size={19} strokeWidth={1.8} /><span>Người dùng</span><ChevronLeft size={14} className="nav-chevron" /></NavLink> : null}
      </nav>
      <div className="sidebar-bottom">
        <div className="system-mini"><div className="system-mini-icon"><Activity size={18} /></div><div><strong>Trạng thái hệ thống</strong><span>{snapshot?.mqtt_connected ? 'MQTT đang kết nối' : 'Chưa kết nối MQTT'}</span></div><i className={snapshot?.mqtt_connected ? 'pulse-dot' : 'muted-dot'} /></div>
        <div className="sidebar-user"><div className="avatar">{user?.full_name?.[0] || user?.username[0] || 'U'}</div><div><strong>{user?.full_name || user?.username}</strong><span>{user?.role}</span></div><button aria-label="Đăng xuất" title="Đăng xuất" onClick={signOut}><LogOut size={18} /></button></div>
      </div>
    </aside>
    <div className="app-main">
      <header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" aria-label="Mở menu" onClick={() => setMenuOpen(true)}><Menu size={21} /></button><div className="breadcrumb"><span>SMART HOME</span><span className="breadcrumb-divider">/</span><strong>{[...links, { to: '/users', label: 'Người dùng', icon: CircleUserRound }].find((item) => item.to === location.pathname)?.label || 'Tổng quan'}</strong></div></div><div className="topbar-right"><div className={`connection-pill ${apiOnline ? 'online' : 'offline'}`}>{apiOnline ? <Wifi size={15} /> : <WifiOff size={15} />}<span>{apiOnline ? 'Backend online' : 'Backend offline'}</span></div><span className="topbar-separator" /><button className="alert-button" aria-label={`${alerts?.unread_count || 0} cảnh báo chưa đọc`} onClick={() => navigate('/security')}><Bell size={19} />{alerts?.unread_count ? <span>{alerts.unread_count}</span> : null}</button><div className="header-avatar" title={user?.username}>{user?.full_name?.[0] || user?.username[0]}</div></div></header>
      <main className="content"><Outlet /></main>
      <footer className="app-footer"><span><Camera size={14} /> Hệ thống 3 cụm ESP32</span><span>{socketStatus === 'connected' ? 'Dữ liệu trực tiếp' : 'Đang dùng cập nhật định kỳ'} · {lastUpdated ? `Cập nhật ${formatTime(lastUpdated.toISOString())}` : 'Chưa cập nhật'}</span></footer>
    </div>
  </div>
}
