import { useState } from 'react'
import { BellRing, Camera, DoorOpen, Fan, Lightbulb, LockKeyhole, RefreshCw, Shield, WifiOff } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useLive } from '../LiveContext'
import { useToast } from '../ToastContext'
import { api, apiError, formatTime } from '../api'
import { Badge, Empty, PageHeading, Panel, StateBadge, Toggle } from '../components/ui'
import type { ClusterId, Mode } from '../types'

function PendingMessage({ cluster }: { cluster: ClusterId }) {
  const { pending } = useLive()
  const entry = pending[cluster]
  if (!entry) return null
  return <div className={`command-notice ${entry.status}`} role="status">{entry.status === 'waiting' ? 'Đang gửi lệnh, chờ ESP32 xác nhận...' : entry.error || 'Trạng thái chưa được xác nhận.'}</div>
}

export function DevicesPage() {
  const { user } = useAuth()
  const { nodeView, pending, sendCommand, refresh, snapshot } = useLive()
  const notify = useToast()
  const [busyCapture, setBusyCapture] = useState(false)
  const c1 = nodeView('esp32_cluster1')
  const c2 = nodeView('esp32_cluster2')
  const cam = nodeView('esp32_cam_01')
  const operator = user?.role !== 'GUEST'

  async function control(cluster: 'esp32_cluster1' | 'esp32_cluster2', body: Record<string, unknown>, expected: { mode?: Mode; outputs?: Record<string, boolean> }) {
    try { await sendCommand(cluster, `/api/mqtt/${cluster === 'esp32_cluster1' ? 'cluster1' : 'cluster2'}/control`, body, expected) }
    catch (error) { notify(apiError(error), 'error') }
  }

  async function door(open: boolean) {
    try { await sendCommand('esp32_cam_01', '/api/mqtt/cam/door', { identity: 'KNOWN', authorized: open, close: !open, person_name: user?.full_name || user?.username || 'Web', confidence: 1 }, { door_state: open ? 'OPEN' : 'LOCKED' }) }
    catch (error) { notify(apiError(error), 'error') }
  }

  async function capture() {
    setBusyCapture(true)
    try { await api.post('/api/mqtt/cam/capture'); notify('Đã gửi yêu cầu chụp ảnh. Đang chờ ESP32-CAM.', 'info') }
    catch (error) { notify(apiError(error), 'error') }
    finally { setBusyCapture(false) }
  }

  const disabled1 = !operator || !c1?.online || pending.esp32_cluster1?.status === 'waiting'
  const disabled2 = !operator || !c2?.online || pending.esp32_cluster2?.status === 'waiting'
  const disabledCam = !operator || !cam?.online || pending.esp32_cam_01?.status === 'waiting'

  return <div className="page-wrap"><PageHeading eyebrow="THIẾT BỊ & ĐIỀU KHIỂN" title="Quản lý thiết bị" description="Lệnh được gửi qua Backend và MQTT. Trạng thái chỉ đổi khi thiết bị xác nhận." action={<button className="button button-secondary" onClick={() => void refresh()}><RefreshCw size={16} /> Làm mới</button>} />
    {!snapshot ? <Empty title="Chưa kết nối Backend" description="Khởi động backend và simulator để thử điều khiển." /> : null}
    {user?.role === 'GUEST' ? <div className="info-strip"><Shield size={18} /> Tài khoản GUEST chỉ có quyền xem. Liên hệ quản trị viên để điều khiển thiết bị.</div> : null}
    <div className="device-grid"><Panel className="device-panel" title="Cụm 1 · An ninh chuyển động" subtitle="PIR GPIO27 · Đèn GPIO26 · Còi GPIO25" action={<StateBadge online={Boolean(c1?.online)} />}><div className="device-sensor"><div className="device-icon icon-amber"><BellRing size={24} /></div><div><strong>{c1?.pir ? 'Đang có chuyển động' : 'Không có chuyển động'}</strong><span>Cảm biến PIR · {c1?.updated_at ? formatTime(c1.updated_at) : 'Chưa có dữ liệu'}</span></div><Badge tone={c1?.pir ? 'danger' : 'success'}>{c1?.pir ? 'CẢNH BÁO' : 'BÌNH THƯỜNG'}</Badge></div><div className="mode-row"><div><strong>Chế độ hoạt động</strong><span>AUTO theo kịch bản hoặc MANUAL từ giao diện</span></div><div className="segmented"><button className={c1?.mode === 'AUTO' ? 'selected' : ''} disabled={disabled1} onClick={() => void control('esp32_cluster1', { mode: 'AUTO' }, { mode: 'AUTO' })}>AUTO</button><button className={c1?.mode === 'MANUAL' ? 'selected' : ''} disabled={disabled1} onClick={() => void control('esp32_cluster1', { mode: 'MANUAL' }, { mode: 'MANUAL' })}>MANUAL</button></div></div><div className="switch-list"><div className="switch-row"><span className="switch-icon"><Lightbulb size={20} /></span><div><strong>Đèn cảnh báo</strong><small>{c1?.outputs.light ? 'Đang bật' : 'Đang tắt'}</small></div><Toggle label="Bật hoặc tắt đèn cảnh báo" checked={Boolean(c1?.outputs.light)} disabled={disabled1} onChange={(value) => void control('esp32_cluster1', { mode: 'MANUAL', light: value }, { mode: 'MANUAL', outputs: { light: value } })} /></div><div className="switch-row"><span className="switch-icon"><BellRing size={20} /></span><div><strong>Còi buzzer</strong><small>{c1?.outputs.buzzer ? 'Đang kêu' : 'Đang tắt'}</small></div><Toggle label="Bật hoặc tắt còi buzzer" checked={Boolean(c1?.outputs.buzzer)} disabled={disabled1} onChange={(value) => void control('esp32_cluster1', { mode: 'MANUAL', buzzer: value }, { mode: 'MANUAL', outputs: { buzzer: value } })} /></div></div><PendingMessage cluster="esp32_cluster1" /></Panel>
      <Panel className="device-panel" title="Cụm 2 · Môi trường & phòng" subtitle="DHT22 · LDR/BH1750 · Đèn GPIO2 · Quạt GPIO5" action={<StateBadge online={Boolean(c2?.online)} />}><div className="device-sensor"><div className="device-icon icon-teal"><Fan size={24} /></div><div><strong>{c2?.temperature_c == null ? 'Chưa có dữ liệu môi trường' : `${c2.temperature_c.toFixed(1)}°C · ${c2.humidity_pct?.toFixed(1) ?? '—'}% độ ẩm`}</strong><span>Ánh sáng: {c2?.light_lux?.toFixed(1) ?? '—'} lux · LDR {c2?.light_adc ?? '—'} ADC</span></div><Badge tone={c2?.is_dark ? 'warning' : 'info'}>{c2?.is_dark ? 'TRỜI TỐI' : 'TRỜI SÁNG'}</Badge></div><div className="mode-row"><div><strong>Chế độ hoạt động</strong><span>Điều khiển theo nhiệt độ và ánh sáng</span></div><div className="segmented"><button className={c2?.mode === 'AUTO' ? 'selected' : ''} disabled={disabled2} onClick={() => void control('esp32_cluster2', { mode: 'AUTO' }, { mode: 'AUTO' })}>AUTO</button><button className={c2?.mode === 'MANUAL' ? 'selected' : ''} disabled={disabled2} onClick={() => void control('esp32_cluster2', { mode: 'MANUAL' }, { mode: 'MANUAL' })}>MANUAL</button></div></div><div className="switch-list"><div className="switch-row"><span className="switch-icon"><Lightbulb size={20} /></span><div><strong>Đèn phòng</strong><small>{c2?.outputs.light ? 'Đang bật' : 'Đang tắt'}</small></div><Toggle label="Bật hoặc tắt đèn phòng" checked={Boolean(c2?.outputs.light)} disabled={disabled2} onChange={(value) => void control('esp32_cluster2', { mode: 'MANUAL', light: value }, { mode: 'MANUAL', outputs: { light: value } })} /></div><div className="switch-row"><span className="switch-icon"><Fan size={20} /></span><div><strong>Quạt làm mát</strong><small>{c2?.outputs.fan ? 'Đang bật' : 'Đang tắt'}</small></div><Toggle label="Bật hoặc tắt quạt" checked={Boolean(c2?.outputs.fan)} disabled={disabled2} onChange={(value) => void control('esp32_cluster2', { mode: 'MANUAL', fan: value }, { mode: 'MANUAL', outputs: { fan: value } })} /></div></div><PendingMessage cluster="esp32_cluster2" /></Panel>
      <Panel className="device-panel camera-device-panel" title="ESP32-CAM · Cửa ra vào" subtitle="Camera AI · Servo SG90 GPIO13" action={<StateBadge online={Boolean(cam?.online)} />}><div className="camera-status"><span className="camera-status-icon"><Camera size={26} /></span><div><strong>{cam?.door_state === 'OPEN' ? 'Cửa đang mở' : 'Cửa đã khóa'}</strong><p>Góc servo {cam?.servo_angle_deg ?? 0}° · Camera {cam?.camera_ready ? 'sẵn sàng' : 'chưa sẵn sàng'}</p></div><Badge tone={cam?.door_state === 'OPEN' ? 'warning' : 'success'}>{cam?.door_state || 'LOCKED'}</Badge></div><div className="door-actions"><button className="button button-primary" disabled={disabledCam} onClick={() => void door(true)}><DoorOpen size={17} /> Mở cửa 5 giây</button><button className="button button-secondary" disabled={disabledCam} onClick={() => void door(false)}><LockKeyhole size={17} /> Khóa cửa</button><button className="button button-quiet" disabled={disabledCam || busyCapture} onClick={() => void capture()}><Camera size={17} /> Chụp ảnh</button></div><PendingMessage cluster="esp32_cam_01" /></Panel></div>
    {!snapshot?.mqtt_connected ? <div className="info-strip warning"><WifiOff size={18} /> Broker MQTT chưa kết nối. Lệnh điều khiển có thể không đến thiết bị.</div> : null}
  </div>
}
