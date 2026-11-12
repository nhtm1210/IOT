import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Eye, EyeOff, House, LockKeyhole, ShieldCheck, Wifi } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { apiError } from '../api'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!username.trim() || !password) { setError('Vui lòng nhập tên đăng nhập và mật khẩu.'); return }
    setBusy(true)
    setError('')
    try { await login(username, password); navigate('/dashboard', { replace: true }) }
    catch (reason) { setError(apiError(reason)) }
    finally { setBusy(false) }
  }

  return <div className="login-page"><div className="login-showcase"><div className="login-brand"><div className="brand-mark"><House size={24} /></div><span>SMARTHOME<span className="accent-dot">.</span></span></div><div className="login-showcase-content"><div className="showcase-orbit"><div className="orbit-ring orbit-one" /><div className="orbit-ring orbit-two" /><div className="orbit-home"><House size={48} strokeWidth={1.4} /></div><span className="orbit-node node-one"><Wifi size={19} /></span><span className="orbit-node node-two"><ShieldCheck size={19} /></span><span className="orbit-node node-three"><LockKeyhole size={19} /></span></div><p className="eyebrow">TRUNG TÂM ĐIỀU KHIỂN</p><h1>Ngôi nhà của bạn.<br /><span>Trong tầm kiểm soát.</span></h1><p>Giám sát môi trường, bảo mật và điều khiển ba cụm ESP32 từ một giao diện duy nhất.</p></div><div className="showcase-footer">Smart Home IoT AI <span>•</span> Dashboard</div></div><div className="login-form-side"><div className="login-card"><div className="login-mobile-brand"><div className="brand-mark"><House size={20} /></div><strong>SMARTHOME.</strong></div><span className="login-lock"><LockKeyhole size={22} /></span><p className="eyebrow">CHÀO MỪNG TRỞ LẠI</p><h2>Đăng nhập hệ thống</h2><p className="login-intro">Sử dụng tài khoản được cấp để truy cập bảng điều khiển.</p><form onSubmit={submit}><label htmlFor="username">Tên đăng nhập</label><input id="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Nhập tên đăng nhập" disabled={busy} /><label htmlFor="password">Mật khẩu</label><div className="password-input"><input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Nhập mật khẩu" disabled={busy} /><button type="button" aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>{error ? <p className="form-error" role="alert">{error}</p> : null}<button className="button button-primary login-submit" disabled={busy} type="submit">{busy ? 'Đang đăng nhập...' : 'Đăng nhập'}<ArrowRight size={18} /></button></form><p className="login-help">Không có tài khoản? Liên hệ quản trị viên của hệ thống.</p></div></div></div>
}
