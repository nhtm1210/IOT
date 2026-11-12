import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, Camera, Check, DoorOpen, ImagePlus, LockKeyhole, RefreshCw, ShieldAlert, UserRound, Upload } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useLive } from '../LiveContext'
import { useToast } from '../ToastContext'
import { api, apiError, formatTime, imageUrl, API_BASE_URL } from '../api'
import { Badge, Empty, InlineError, Loading, PageHeading, Panel, StateBadge } from '../components/ui'
import type { Alert, AlertsResponse, Recognition } from '../types'

const identityLabel: Record<string, string> = { KNOWN: 'Chủ nhà', UNKNOWN: 'Người lạ', NO_FACE: 'Không có khuôn mặt', NONE: 'Chưa nhận diện' }

export function SecurityPage() {
  const { user } = useAuth()
  const { nodeView, snapshot, refresh } = useLive()
  const notify = useToast()
  const cam = nodeView('esp32_cam_01')
  const operator = user?.role !== 'GUEST'
  const [recognitions, setRecognitions] = useState<Recognition[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [ownerImageVersion, setOwnerImageVersion] = useState(Date.now())
  const enrollInput = useRef<HTMLInputElement>(null)
  const recognizeInput = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setError('')
    try {
      const [recognitionRes, alertRes] = await Promise.all([api.get<Recognition[]>('/api/recognitions?limit=25'), api.get<AlertsResponse>('/api/alerts?limit=25')])
      setRecognitions(recognitionRes.data)
      setAlerts(alertRes.data.items)
    } catch (reason) { setError(apiError(reason)) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void load(); const timer = window.setInterval(() => { void load() }, 20000); return () => window.clearInterval(timer) }, [load])

  async function upload(file: File, mode: 'enroll' | 'recognize') {
    if (!file.type.startsWith('image/')) { notify('Vui lòng chọn tệp ảnh.', 'error'); return }
    setBusy(mode)
    const form = new FormData()
    form.append('file', file)
    try {
      if (mode === 'enroll') {
        await api.post('/api/security/enroll?person_name=Chu_Nha', form)
        setOwnerImageVersion(Date.now())
        notify('Đã lưu ảnh mẫu chủ nhà.', 'success')
      } else {
        await api.post('/api/security/recognize', form)
        notify('Đã gửi ảnh nhận diện. Kiểm tra kết quả và trạng thái cửa.', 'success')
      }
      await Promise.all([load(), refresh()])
    } catch (reason) { notify(apiError(reason), 'error') }
    finally { setBusy('') }
  }

  async function capture() {
    setBusy('capture')
    try { await api.post('/api/mqtt/cam/capture'); notify('Đã yêu cầu ESP32-CAM chụp ảnh. Chờ camera gửi về.', 'info') }
    catch (reason) { notify(apiError(reason), 'error') }
    finally { setBusy('') }
  }

  async function markRead(alert: Alert) {
    try { await api.put(`/api/alerts/${alert.id}/read`); setAlerts((current) => current.map((item) => item.id === alert.id ? { ...item, is_read: true } : item)) }
    catch (reason) { notify(apiError(reason), 'error') }
  }

  const latestRecognition = recognitions[0]
  const captureImage = imageUrl(cam?.last_image_url || latestRecognition?.image_url)
  return <div className="page-wrap"><PageHeading eyebrow="AI & AN NINH" title="Trung tâm an ninh" description="Theo dõi camera, nhận diện khuôn mặt và các cảnh báo trong nhà." action={<button className="button button-secondary" onClick={() => void Promise.all([load(), refresh()])}><RefreshCw size={16} /> Làm mới</button>} />
    {loading ? <Loading /> : null}{error ? <InlineError message={error} onRetry={() => void load()} /> : null}
    <div className="security-hero-grid"><Panel title="Camera ESP32-CAM" subtitle="Hình ảnh và trạng thái gần nhất" action={<StateBadge online={Boolean(cam?.online)} />}><div className="security-image">{captureImage ? <img src={captureImage} alt="Ảnh chụp gần nhất từ ESP32-CAM" /> : <div className="camera-placeholder"><Camera size={40} /><span>Chưa có ảnh từ ESP32-CAM</span></div>}</div><div className="camera-actions"><button className="button button-primary" disabled={!operator || !cam?.online || Boolean(busy)} onClick={() => void capture()}><Camera size={17} />{busy === 'capture' ? 'Đang gửi...' : 'Chụp từ camera'}</button><button className="button button-secondary" disabled={!operator || Boolean(busy)} onClick={() => recognizeInput.current?.click()}><Upload size={17} /> Nhận diện ảnh tải lên</button><input ref={recognizeInput} type="file" accept="image/*" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file, 'recognize'); event.target.value = '' }} /></div><p className="muted-note">Chỉ dùng ảnh của người đã đồng ý tham gia. Kết quả và trạng thái cửa sẽ cập nhật sau khi hệ thống xử lý.</p></Panel>
      <div className="security-info-stack"><Panel title="Kết quả nhận diện" subtitle="Phản hồi mới nhất từ camera"><div className="identity-result"><div className={`identity-icon identity-${cam?.last_identity || 'NONE'}`}><UserRound size={30} /></div><div><span>KẾT QUẢ GẦN NHẤT</span><strong>{identityLabel[cam?.last_identity || 'NONE'] || cam?.last_identity}</strong><p>{cam?.last_person_name || 'Chưa xác định'} · {cam?.last_confidence != null ? `${Math.round(cam.last_confidence * 100)}% tin cậy` : 'Chưa có độ tin cậy'}</p></div></div><div className="security-facts"><div><span>Trạng thái cửa</span><Badge tone={cam?.door_state === 'OPEN' ? 'warning' : 'success'}>{cam?.door_state === 'OPEN' ? <><DoorOpen size={14} /> ĐANG MỞ</> : <><LockKeyhole size={14} /> ĐÃ KHÓA</>}</Badge></div><div><span>Góc servo</span><strong>{cam?.servo_angle_deg ?? 0}°</strong></div><div><span>Cập nhật</span><strong>{formatTime(cam?.updated_at)}</strong></div></div></Panel><Panel title="Ảnh mẫu chủ nhà" subtitle="Dùng để đối chiếu khi nhận diện"><div className="owner-face-row">{snapshot?.owner_face_enrolled ? <img src={`${API_BASE_URL}/api/security/owner-face?t=${ownerImageVersion}`} alt="Ảnh mẫu chủ nhà" /> : <span className="owner-placeholder"><ImagePlus size={24} /></span>}<div><strong>{snapshot?.owner_face_enrolled ? 'Đã lưu ảnh mẫu' : 'Chưa có ảnh mẫu'}</strong><span>Chỉ tải ảnh của người đã đồng ý tham gia.</span></div></div><button className="button button-secondary button-full" disabled={!operator || Boolean(busy)} onClick={() => enrollInput.current?.click()}><ImagePlus size={17} /> {busy === 'enroll' ? 'Đang lưu...' : 'Tải ảnh mẫu chủ nhà'}</button><input ref={enrollInput} type="file" accept="image/*" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file, 'enroll'); event.target.value = '' }} /></Panel></div></div>
    <div className="security-bottom-grid"><Panel title="Lịch sử nhận diện" subtitle="Các sự kiện gần đây">{recognitions.length ? <div className="event-list">{recognitions.slice(0, 8).map((item) => <div className="event-row" key={item.id}><div className={`event-icon identity-${item.identity}`}><UserRound size={18} /></div><div className="event-main"><strong>{identityLabel[item.identity] || item.identity} {item.person_name ? `· ${item.person_name}` : ''}</strong><span>{formatTime(item.created_at, true)} · {Math.round(item.confidence * 100)}% tin cậy</span></div><Badge tone={item.identity === 'KNOWN' ? 'success' : item.identity === 'UNKNOWN' ? 'danger' : 'neutral'}>{item.door_state}</Badge></div>)}</div> : <Empty title="Chưa có lịch sử nhận diện" />}</Panel><Panel title="Cảnh báo" subtitle="Sự kiện an ninh và môi trường">{alerts.length ? <div className="event-list">{alerts.slice(0, 8).map((alert) => <div className="event-row" key={alert.id}><div className={`event-icon alert-${alert.severity.toLowerCase()}`}><Bell size={18} /></div><div className="event-main"><strong>{alert.title}</strong><span>{alert.message}</span><small>{formatTime(alert.created_at, true)}</small></div>{!alert.is_read ? <button className="icon-button" title="Đánh dấu đã đọc" aria-label={`Đánh dấu đã đọc: ${alert.title}`} onClick={() => void markRead(alert)}><Check size={17} /></button> : <Badge tone="neutral">Đã đọc</Badge>}</div>)}</div> : <Empty title="Chưa có cảnh báo" />}</Panel></div>
    {user?.role === 'GUEST' ? <div className="info-strip"><ShieldAlert size={18} /> Tài khoản GUEST chỉ xem trạng thái và lịch sử.</div> : null}
  </div>
}
