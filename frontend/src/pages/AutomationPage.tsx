import { useCallback, useEffect, useState } from 'react'
import { BellRing, Camera, Fan, Lightbulb, RefreshCw, Save, ShieldAlert } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useToast } from '../ToastContext'
import { api, apiError, formatTime } from '../api'
import { Badge, Empty, InlineError, Loading, PageHeading, Panel, Toggle } from '../components/ui'
import type { AutomationRule, Settings } from '../types'

interface RuleField { key: string; label: string; unit?: string; min?: number; max?: number; step?: number; kind?: 'boolean' }
const fields: Record<string, RuleField[]> = {
  RULE_C1_PIR_ALARM: [
    { key: 'hold_seconds', label: 'Giữ đèn/còi sau chuyển động', unit: 'giây', min: 1, max: 300, step: 1 },
    { key: 'turn_on_light', label: 'Bật đèn cảnh báo', kind: 'boolean' },
    { key: 'turn_on_buzzer', label: 'Bật còi buzzer', kind: 'boolean' },
    { key: 'trigger_camera_capture', label: 'Yêu cầu camera chụp ảnh', kind: 'boolean' },
  ],
  RULE_C2_TEMP_HUM_FAN: [
    { key: 'temp_threshold_c', label: 'Nhiệt độ bật quạt', unit: '°C', min: 0, max: 100, step: 0.1 },
    { key: 'humidity_max_pct', label: 'Độ ẩm tối đa', unit: '%', min: 0, max: 100, step: 0.1 },
  ],
  RULE_C2_LIGHT_LDR: [
    { key: 'light_adc_threshold', label: 'Ngưỡng tối LDR', unit: 'ADC', min: 0, max: 4095, step: 1 },
    { key: 'light_lux_threshold', label: 'Ngưỡng lux tham khảo', unit: 'lux', min: 0, max: 100000, step: 1 },
  ],
  RULE_CAM_FACE_DOOR: [
    { key: 'confidence_threshold', label: 'Độ tin cậy tối thiểu', unit: '0–1', min: 0.1, max: 0.99, step: 0.01 },
    { key: 'open_duration_sec', label: 'Thời gian mở cửa', unit: 'giây', min: 1, max: 60, step: 1 },
    { key: 'alert_on_unknown', label: 'Cảnh báo người lạ', kind: 'boolean' },
  ],
}
const icons: Record<string, typeof BellRing> = { RULE_C1_PIR_ALARM: BellRing, RULE_C2_TEMP_HUM_FAN: Fan, RULE_C2_LIGHT_LDR: Lightbulb, RULE_CAM_FACE_DOOR: Camera }

export function AutomationPage() {
  const { user } = useAuth()
  const notify = useToast()
  const [rules, setRules] = useState<AutomationRule[]>([])
  const [drafts, setDrafts] = useState<Record<number, AutomationRule>>({})
  const [settings, setSettings] = useState<Settings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState<number | 'security' | null>(null)
  const operator = user?.role !== 'GUEST'

  const load = useCallback(async () => {
    setError('')
    try {
      const [rulesRes, settingsRes] = await Promise.all([api.get<AutomationRule[]>('/api/automation/rules'), api.get<Settings>('/api/settings')])
      setRules(rulesRes.data)
      setDrafts(Object.fromEntries(rulesRes.data.map((rule) => [rule.id, { ...rule, config: { ...rule.config } }])))
      setSettings(settingsRes.data)
    } catch (reason) { setError(apiError(reason)) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void load() }, [load])

  function updateRule(id: number, patch: Partial<AutomationRule>) {
    setDrafts((current) => ({ ...current, [id]: { ...current[id], ...patch } }))
  }
  function updateConfig(id: number, key: string, value: number | boolean) {
    setDrafts((current) => ({ ...current, [id]: { ...current[id], config: { ...current[id].config, [key]: value } } }))
  }

  async function saveRule(rule: AutomationRule) {
    const draft = drafts[rule.id]
    for (const field of fields[rule.code] || []) {
      if (field.kind === 'boolean') continue
      const value = Number(draft.config[field.key])
      if (!Number.isFinite(value) || value < (field.min ?? -Infinity) || value > (field.max ?? Infinity)) {
        notify(`${field.label} phải trong khoảng ${field.min}–${field.max}.`, 'error'); return
      }
    }
    setSaving(rule.id)
    try {
      const { data } = await api.put<AutomationRule>(`/api/automation/rules/${rule.id}`, { is_enabled: draft.is_enabled, config: draft.config })
      setRules((current) => current.map((item) => item.id === data.id ? data : item))
      setDrafts((current) => ({ ...current, [data.id]: { ...data, config: { ...data.config } } }))
      notify('Đã lưu quy tắc tự động hóa.', 'success')
    } catch (reason) { notify(apiError(reason), 'error') }
    finally { setSaving(null) }
  }

  async function updateSecurity(key: 'security_armed' | 'telegram_enabled', value: boolean) {
    if (!settings) return
    setSaving('security')
    try {
      const { data } = await api.put<Settings>('/api/settings', { [key]: value })
      setSettings(data)
      notify('Đã lưu chế độ bảo mật.', 'success')
    } catch (reason) { notify(apiError(reason), 'error') }
    finally { setSaving(null) }
  }

  return <div className="page-wrap"><PageHeading eyebrow="TỰ ĐỘNG HÓA" title="Kịch bản thông minh" description="Bật tắt và điều chỉnh các quy tắc đang chạy trên ba cụm ESP32." action={<button className="button button-secondary" onClick={() => void load()}><RefreshCw size={16} /> Tải lại</button>} />
    {loading ? <Loading /> : null}{error ? <InlineError message={error} onRetry={() => void load()} /> : null}
    {!loading && !rules.length && !error ? <Empty title="Chưa có kịch bản" description="Backend chưa trả về quy tắc tự động hóa." /> : null}
    <div className="automation-grid">{rules.map((rule) => { const draft = drafts[rule.id]; if (!draft) return null; const Icon = icons[rule.code] || ShieldAlert; const dirty = JSON.stringify({ enabled: draft.is_enabled, config: draft.config }) !== JSON.stringify({ enabled: rule.is_enabled, config: rule.config }); return <Panel key={rule.id} className="rule-panel" title={rule.name.replace(/^Kịch bản /, '')} subtitle={rule.cluster_id} action={<Badge tone={draft.is_enabled ? 'success' : 'neutral'}>{draft.is_enabled ? 'ĐANG BẬT' : 'TẠM TẮT'}</Badge>}><div className="rule-icon"><Icon size={22} /></div><p className="rule-description">{rule.description}</p><div className="rule-enable"><div><strong>Kích hoạt kịch bản</strong><span>Quy tắc sẽ áp dụng khi cụm ở chế độ AUTO</span></div><Toggle label={`Kích hoạt ${rule.name}`} checked={draft.is_enabled} disabled={!operator || saving !== null} onChange={(value) => updateRule(rule.id, { is_enabled: value })} /></div><div className="rule-fields">{(fields[rule.code] || []).map((field) => <div className="rule-field" key={field.key}><label htmlFor={`${rule.id}-${field.key}`}>{field.label}</label>{field.kind === 'boolean' ? <Toggle label={field.label} checked={Boolean(draft.config[field.key])} disabled={!operator || saving !== null} onChange={(value) => updateConfig(rule.id, field.key, value)} /> : <div className="field-with-unit"><input id={`${rule.id}-${field.key}`} type="number" min={field.min} max={field.max} step={field.step} value={draft.config[field.key] == null ? '' : String(draft.config[field.key])} disabled={!operator || saving !== null} onChange={(event) => updateConfig(rule.id, field.key, Number(event.target.value))} /><span>{field.unit}</span></div>}</div>)}</div><div className="rule-footer"><span>Cập nhật {formatTime(rule.updated_at, true)}</span><button className="button button-primary button-small" disabled={!operator || !dirty || saving !== null} onClick={() => void saveRule(rule)}><Save size={15} /> {saving === rule.id ? 'Đang lưu...' : 'Lưu thay đổi'}</button></div></Panel> })}</div>
    {settings ? <Panel className="security-settings-panel" title="Bảo mật hệ thống" subtitle="Các công tắc chung được lưu tại Backend"><div className="security-settings-grid"><div className="switch-row"><span className="switch-icon"><ShieldAlert size={20} /></span><div><strong>Bật chế độ bảo mật</strong><small>Cho phép xử lý cảnh báo nhận diện</small></div><Toggle label="Bật chế độ bảo mật" checked={settings.security_armed} disabled={!operator || saving !== null} onChange={(value) => void updateSecurity('security_armed', value)} /></div><div className="switch-row"><span className="switch-icon"><BellRing size={20} /></span><div><strong>Gửi cảnh báo Telegram</strong><small>Cần cấu hình bot trong trang Cài đặt</small></div><Toggle label="Gửi cảnh báo Telegram" checked={settings.telegram_enabled} disabled={!operator || saving !== null} onChange={(value) => void updateSecurity('telegram_enabled', value)} /></div></div></Panel> : null}
  </div>
}
