import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Plus, RefreshCw, Save, Trash2, UserRound, Users } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useToast } from '../ToastContext'
import { api, apiError, formatTime } from '../api'
import { Badge, Empty, InlineError, Loading, PageHeading, Panel } from '../components/ui'
import type { Role, User } from '../types'

interface NewUser { username: string; full_name: string; password: string; role: Role }
const blank: NewUser = { username: '', full_name: '', password: '', role: 'USER' }

export function UsersPage() {
  const { user: currentUser } = useAuth()
  const notify = useToast()
  const [users, setUsers] = useState<User[]>([])
  const [newUser, setNewUser] = useState<NewUser>(blank)
  const [editing, setEditing] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editRole, setEditRole] = useState<Role>('USER')
  const [editActive, setEditActive] = useState(true)
  const [editPassword, setEditPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try { const { data } = await api.get<User[]>('/api/users'); setUsers(data) }
    catch (reason) { setError(apiError(reason)) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void load() }, [load])

  async function create(event: FormEvent) {
    event.preventDefault()
    if (newUser.username.trim().length < 3 || newUser.password.length < 4) { notify('Tên đăng nhập cần ít nhất 3 ký tự và mật khẩu ít nhất 4 ký tự.', 'error'); return }
    setBusy(true)
    try { await api.post('/api/users', newUser); setNewUser(blank); await load(); notify('Đã tạo tài khoản.', 'success') }
    catch (reason) { notify(apiError(reason), 'error') }
    finally { setBusy(false) }
  }

  function beginEdit(user: User) { setEditing(user.id); setEditName(user.full_name); setEditRole(user.role); setEditActive(user.is_active); setEditPassword('') }
  async function save() {
    if (editing === null) return
    setBusy(true)
    try { await api.put(`/api/users/${editing}`, { full_name: editName, role: editRole, is_active: editActive, ...(editPassword ? { password: editPassword } : {}) }); setEditing(null); await load(); notify('Đã cập nhật tài khoản.', 'success') }
    catch (reason) { notify(apiError(reason), 'error') }
    finally { setBusy(false) }
  }
  async function remove(user: User) {
    if (!window.confirm(`Xóa tài khoản ${user.username}?`)) return
    setBusy(true)
    try { await api.delete(`/api/users/${user.id}`); await load(); notify('Đã xóa tài khoản.', 'success') }
    catch (reason) { notify(apiError(reason), 'error') }
    finally { setBusy(false) }
  }

  return <div className="page-wrap"><PageHeading eyebrow="QUẢN TRỊ" title="Người dùng" description="Tạo tài khoản và phân quyền ADMIN, USER, GUEST." action={<button className="button button-secondary" onClick={() => void load()}><RefreshCw size={16} /> Tải lại</button>} />{loading ? <Loading /> : null}{error ? <InlineError message={error} onRetry={() => void load()} /> : null}<div className="users-grid"><Panel title="Danh sách tài khoản" subtitle={`${users.length} tài khoản trong hệ thống`} action={<Users size={20} className="panel-heading-icon" />}>{users.length ? <div className="users-list">{users.map((user) => <div className="user-row" key={user.id}><span className="avatar">{user.full_name?.[0] || user.username[0]}</span><div className="user-row-main"><strong>{user.full_name || user.username}</strong><span>@{user.username} · Tạo {formatTime(user.created_at, true)}</span></div><Badge tone={user.is_active ? 'success' : 'neutral'}>{user.role}</Badge><div className="user-row-actions"><button className="button button-quiet button-small" disabled={busy} onClick={() => beginEdit(user)}>Sửa</button><button className="icon-button" title="Xóa tài khoản" aria-label={`Xóa ${user.username}`} disabled={busy || user.id === currentUser?.id || user.username === 'admin'} onClick={() => void remove(user)}><Trash2 size={17} /></button></div></div>)}</div> : <Empty title="Chưa có tài khoản" />}</Panel><Panel title={editing === null ? 'Thêm người dùng' : 'Sửa người dùng'} subtitle={editing === null ? 'Tạo tài khoản mới theo quyền phù hợp' : 'Cập nhật thông tin tài khoản'} action={<UserRound size={20} className="panel-heading-icon" />}>{editing === null ? <form className="user-form" onSubmit={create}><label>Tên đăng nhập<input required minLength={3} value={newUser.username} onChange={(event) => setNewUser({ ...newUser, username: event.target.value })} /></label><label>Họ tên<input value={newUser.full_name} onChange={(event) => setNewUser({ ...newUser, full_name: event.target.value })} /></label><label>Mật khẩu<input type="password" required minLength={4} value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} /></label><label>Vai trò<select value={newUser.role} onChange={(event) => setNewUser({ ...newUser, role: event.target.value as Role })}><option value="USER">USER · Điều khiển</option><option value="GUEST">GUEST · Chỉ xem</option><option value="ADMIN">ADMIN · Quản trị</option></select></label><button className="button button-primary" type="submit" disabled={busy}><Plus size={17} /> Tạo tài khoản</button></form> : <div className="user-form"><label>Họ tên<input value={editName} onChange={(event) => setEditName(event.target.value)} /></label><label>Vai trò<select value={editRole} onChange={(event) => setEditRole(event.target.value as Role)}><option value="USER">USER</option><option value="GUEST">GUEST</option><option value="ADMIN">ADMIN</option></select></label><label>Mật khẩu mới<input type="password" placeholder="Để trống nếu không đổi" value={editPassword} onChange={(event) => setEditPassword(event.target.value)} /></label><label className="checkbox-label"><input type="checkbox" checked={editActive} onChange={(event) => setEditActive(event.target.checked)} /> Tài khoản đang hoạt động</label><div className="edit-actions"><button className="button button-secondary" disabled={busy} onClick={() => setEditing(null)}>Hủy</button><button className="button button-primary" disabled={busy} onClick={() => void save()}><Save size={16} /> Lưu thay đổi</button></div></div>}</Panel></div></div>
}
