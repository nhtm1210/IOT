import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Bell, CircleUserRound, LockKeyhole, RefreshCw, Save, Send, Settings2, Shield } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useToast } from '../ToastContext'
import { api, apiError } from '../api'
import { InlineError, Loading, PageHeading, Panel, Toggle } from '../components/ui'
import type { Settings } from '../types'

export function SettingsPage() {
  const { user } = useAuth()
  const notify = useToast()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [draft, setDraft] = useState<Settings | null>(null)
  const [tokenInput, setTokenInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState('')
  const operator = user?.role !== 'GUEST'

  const load = useCallback(async () => {
    setError('')
    try { const { data } = await api.get<Settings>('/api/settings'); setSettings(data); setDraft({ ...data }); setTokenInput('') }
    catch (reason) { setError(apiError(reason)) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void load() }, [load])

  function setField<K extends keyof Settings>(key: K, value: Settings[K]) { setDraft((current) => current ? { ...current, [key]: value } : current) }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!draft) return
    const limits: Array<[keyof Settings, number, number]> = [['temp_threshold_c', 0, 100], ['humidity_threshold_pct', 0, 100], ['light_adc_threshold', 0, 4095], ['pir_hold_seconds', 1, 300], ['face_match_threshold', 0.1, 0.99], ['door_open_seconds', 1, 60]]
    for (const [key, min, max] of limits) { const value = Number(draft[key]); if (!Number.isFinite(value) || value < min || value > max) { notify(`${key} phải trong khoảng ${min}–${max}.`, 'error'); return } }
    setSaving(true)
    try {
      const payload: Record<string, unknown> = { ...draft }
      delete payload.telegram_bot_token
      if (tokenInput.trim()) payload.telegram_bot_token = tokenInput.trim()
      const { data } = await api.put<Settings>('/api/settings', payload)
      setSettings(data); setDraft({ ...data }); setTokenInput('')
      notify('Đã lưu cài đặt hệ thống.', 'success')
    } catch (reason) { notify(apiError(reason), 'error') }
    finally { setSaving(false) }
  }

  async function testTelegram() {
    setTesting(true)
    try {
      const { data } = await api.post<{ success: boolean; detail: string }>('/api/settings/telegram/test', { message: 'Kiểm tra kết nối từ Smart Home Dashboard' })
      notify(data.detail || (data.success ? 'Đã gửi tin nhắn thử.' : 'Không gửi được tin nhắn thử.'), data.success ? 'success' : 'error')
    } catch (reason) { notify(apiError(reason), 'error') }
    finally { setTesting(false) }
  }

  return <div className="page-wrap"><PageHeading eyebrow="CẤU HÌNH HỆ THỐNG" title="Cài đặt" description="Các thông số được lưu trong Backend và đồng bộ sang quy tắc tự động hóa." action={<button className="button button-secondary" onClick={() => void load()}><RefreshCw size={16} /> Tải lại</button>} />
    {loading ? <Loading /> : null}{error ? <InlineError message={error} onRetry={() => void load()} /> : null}
    {draft ? <form onSubmit={save}><div className="settings-grid"><Panel title="Ngưỡng cảm biến" subtitle="Áp dụng cho tự động hóa Cụm 1 và Cụm 2" action={<Settings2 size={20} className="panel-heading-icon" />}><div className="settings-fields"><label>Nhiệt độ bật quạt <span>°C</span><input type="number" min="0" max="100" step="0.1" value={draft.temp_threshold_c} disabled={!operator || saving} onChange={(event) => setField('temp_threshold_c', Number(event.target.value))} /></label><label>Độ ẩm tối đa <span>%</span><input type="number" min="0" max="100" step="0.1" value={draft.humidity_threshold_pct} disabled={!operator || saving} onChange={(event) => setField('humidity_threshold_pct', Number(event.target.value))} /></label><label>Ngưỡng tối LDR <span>ADC</span><input type="number" min="0" max="4095" step="1" value={draft.light_adc_threshold} disabled={!operator || saving} onChange={(event) => setField('light_adc_threshold', Number(event.target.value))} /></label><label>Giữ đèn/còi sau chuyển động <span>giây</span><input type="number" min="1" max="300" step="1" value={draft.pir_hold_seconds} disabled={!operator || saving} onChange={(event) => setField('pir_hold_seconds', Number(event.target.value))} /></label></div></Panel><Panel title="Camera & bảo mật" subtitle="Ngưỡng nhận diện và thời gian mở cửa" action={<Shield size={20} className="panel-heading-icon" />}><div className="settings-fields"><label>Độ tin cậy nhận diện <span>0–1</span><input type="number" min="0.1" max="0.99" step="0.01" value={draft.face_match_threshold} disabled={!operator || saving} onChange={(event) => setField('face_match_threshold', Number(event.target.value))} /></label><label>Thời gian mở cửa <span>giây</span><input type="number" min="1" max="60" step="1" value={draft.door_open_seconds} disabled={!operator || saving} onChange={(event) => setField('door_open_seconds', Number(event.target.value))} /></label></div><div className="settings-toggle-row"><div><strong>Bật chế độ bảo mật</strong><span>Xử lý sự kiện nhận diện người lạ</span></div><Toggle label="Bật chế độ bảo mật" checked={draft.security_armed} disabled={!operator || saving} onChange={(value) => setField('security_armed', value)} /></div></Panel><Panel title="Thông báo Telegram" subtitle="Cấu hình bot cho cảnh báo bảo mật" action={<Bell size={20} className="panel-heading-icon" />}><div className="settings-toggle-row"><div><strong>Cho phép gửi Telegram</strong><span>Chỉ hoạt động khi bot và chat ID hợp lệ</span></div><Toggle label="Cho phép gửi Telegram" checked={draft.telegram_enabled} disabled={!operator || saving} onChange={(value) => setField('telegram_enabled', value)} /></div><div className="settings-fields"><label>Bot token <span>{settings?.telegram_bot_token ? 'Đã lưu token' : 'Chưa cấu hình'}</span><input type="password" autoComplete="off" value={tokenInput} placeholder="Để trống nếu không đổi token" disabled={!operator || saving} onChange={(event) => setTokenInput(event.target.value)} /></label><label>Chat ID <input type="text" value={draft.telegram_chat_id || ''} placeholder="Nhập Telegram chat ID" disabled={!operator || saving} onChange={(event) => setField('telegram_chat_id', event.target.value)} /></label></div><button type="button" className="button button-secondary" disabled={!operator || testing} onClick={() => void testTelegram()}><Send size={16} /> {testing ? 'Đang gửi...' : 'Gửi tin nhắn thử'}</button></Panel><Panel title="Tài khoản hiện tại" subtitle="Thông tin và quyền truy cập" action={<CircleUserRound size={20} className="panel-heading-icon" />}><div className="account-card"><div className="avatar avatar-large">{user?.full_name?.[0] || user?.username[0]}</div><div><strong>{user?.full_name || user?.username}</strong><span>@{user?.username} · {user?.role}</span></div></div><div className="account-note"><LockKeyhole size={17} /> Quyền điều khiển và sửa cài đặt do Backend kiểm tra.</div></Panel></div><div className="settings-save"><span>{operator ? 'Nhấn lưu để đồng bộ các thay đổi lên Backend.' : 'Tài khoản GUEST chỉ có quyền xem cài đặt.'}</span><button className="button button-primary" disabled={!operator || saving} type="submit"><Save size={17} /> {saving ? 'Đang lưu...' : 'Lưu cài đặt'}</button></div></form> : null}
  </div>
}
