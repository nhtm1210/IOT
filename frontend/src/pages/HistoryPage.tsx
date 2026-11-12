import { useCallback, useEffect, useState } from 'react'
import { Activity, RefreshCw } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, apiError, formatTime } from '../api'
import { Badge, Empty, InlineError, Loading, PageHeading, Panel } from '../components/ui'
import type { AlertsResponse, DeviceHistory, Recognition, SensorHistory } from '../types'

type Tab = 'devices' | 'recognitions' | 'alerts'

export function HistoryPage() {
  const [minutes, setMinutes] = useState(60)
  const [tab, setTab] = useState<Tab>('devices')
  const [sensors, setSensors] = useState<SensorHistory[]>([])
  const [devices, setDevices] = useState<DeviceHistory[]>([])
  const [recognitions, setRecognitions] = useState<Recognition[]>([])
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const [sensorRes, deviceRes, recognitionRes, alertRes] = await Promise.all([
        api.get<SensorHistory[]>('/api/sensors/history', { params: { cluster_id: 'esp32_cluster2', minutes, limit: 120 } }),
        api.get<DeviceHistory[]>('/api/devices/history?limit=50'),
        api.get<Recognition[]>('/api/recognitions?limit=50'),
        api.get<AlertsResponse>('/api/alerts?limit=50'),
      ])
      setSensors(sensorRes.data)
      setDevices(deviceRes.data)
      setRecognitions(recognitionRes.data)
      setAlerts(alertRes.data)
    } catch (reason) { setError(apiError(reason)) }
    finally { setLoading(false) }
  }, [minutes])
  useEffect(() => { void load() }, [load])

  const chartData = sensors.map((item) => ({ ...item, time: formatTime(item.created_at) }))
  return <div className="page-wrap"><PageHeading eyebrow="DỮ LIỆU LƯU TRỮ" title="Lịch sử hoạt động" description="Xem biến thiên cảm biến và nhật ký sự kiện từ Backend." action={<div className="heading-controls"><select aria-label="Khoảng thời gian" value={minutes} onChange={(event) => setMinutes(Number(event.target.value))}><option value={15}>15 phút</option><option value={60}>1 giờ</option><option value={360}>6 giờ</option><option value={1440}>24 giờ</option></select><button className="button button-secondary" onClick={() => void load()}><RefreshCw size={16} /> Làm mới</button></div>} />
    {loading ? <Loading /> : null}{error ? <InlineError message={error} onRetry={() => void load()} /> : null}
    <div className="chart-grid"><Panel title="Nhiệt độ & độ ẩm" subtitle="Dữ liệu từ DHT22 · Cụm 2"><div className="chart-legend"><span><i className="legend-dot temp" /> Nhiệt độ °C</span><span><i className="legend-dot humidity" /> Độ ẩm %</span></div>{chartData.length ? <div className="chart-box"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 8, right: 12, left: -20, bottom: 4 }}><CartesianGrid stroke="#e8edf0" strokeDasharray="4 4" vertical={false} /><XAxis dataKey="time" tick={{ fontSize: 11, fill: '#798896' }} minTickGap={28} /><YAxis tick={{ fontSize: 11, fill: '#798896' }} /><Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #dfe7e9' }} /><Line type="monotone" dataKey="temperature_c" name="Nhiệt độ" stroke="#dc804e" strokeWidth={2.5} dot={false} connectNulls /><Line type="monotone" dataKey="humidity_pct" name="Độ ẩm" stroke="#278a9b" strokeWidth={2.5} dot={false} connectNulls /></LineChart></ResponsiveContainer></div> : <Empty title="Chưa có dữ liệu biểu đồ" description="Chạy simulator hoặc kết nối ESP32 để tạo lịch sử." />}</Panel><Panel title="Cường độ ánh sáng" subtitle="Giá trị LDR ADC · Cụm 2"><div className="chart-legend"><span><i className="legend-dot light" /> Ánh sáng ADC</span></div>{chartData.length ? <div className="chart-box"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ top: 8, right: 12, left: -20, bottom: 4 }}><defs><linearGradient id="lightArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#d8a648" stopOpacity={0.34} /><stop offset="100%" stopColor="#d8a648" stopOpacity={0.02} /></linearGradient></defs><CartesianGrid stroke="#e8edf0" strokeDasharray="4 4" vertical={false} /><XAxis dataKey="time" tick={{ fontSize: 11, fill: '#798896' }} minTickGap={28} /><YAxis tick={{ fontSize: 11, fill: '#798896' }} /><Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #dfe7e9' }} /><Area type="monotone" dataKey="light_adc" name="Ánh sáng ADC" stroke="#d8a648" fill="url(#lightArea)" strokeWidth={2.5} connectNulls /></AreaChart></ResponsiveContainer></div> : <Empty title="Chưa có dữ liệu ánh sáng" />}</Panel></div>
    <Panel className="history-panel" title="Nhật ký sự kiện" subtitle="Lệnh điều khiển, nhận diện AI và cảnh báo"><div className="tabs" role="tablist" aria-label="Loại lịch sử"><button role="tab" aria-selected={tab === 'devices'} className={tab === 'devices' ? 'active' : ''} onClick={() => setTab('devices')}>Thiết bị <span>{devices.length}</span></button><button role="tab" aria-selected={tab === 'recognitions'} className={tab === 'recognitions' ? 'active' : ''} onClick={() => setTab('recognitions')}>Nhận diện <span>{recognitions.length}</span></button><button role="tab" aria-selected={tab === 'alerts'} className={tab === 'alerts' ? 'active' : ''} onClick={() => setTab('alerts')}>Cảnh báo <span>{alerts?.count || 0}</span></button></div><div className="table-scroll">{tab === 'devices' ? devices.length ? <table><thead><tr><th>Thời gian</th><th>Cụm</th><th>Thao tác</th><th>Chế độ</th><th>Người gửi</th><th>Xác nhận</th></tr></thead><tbody>{devices.map((item) => <tr key={item.id}><td>{formatTime(item.created_at, true)}</td><td>{item.cluster_id}</td><td>{item.state}</td><td>{item.mode}</td><td>{item.triggered_by}</td><td><Badge tone={item.ack_received ? item.success ? 'success' : 'danger' : 'warning'}>{item.ack_received ? item.success ? 'ACK thành công' : 'ACK thất bại' : 'Chưa có ACK'}</Badge></td></tr>)}</tbody></table> : <Empty title="Chưa có lệnh điều khiển" /> : null}{tab === 'recognitions' ? recognitions.length ? <table><thead><tr><th>Thời gian</th><th>Danh tính</th><th>Tên</th><th>Độ tin cậy</th><th>Cửa</th></tr></thead><tbody>{recognitions.map((item) => <tr key={item.id}><td>{formatTime(item.created_at, true)}</td><td><Badge tone={item.identity === 'KNOWN' ? 'success' : item.identity === 'UNKNOWN' ? 'danger' : 'neutral'}>{item.identity}</Badge></td><td>{item.person_name || '—'}</td><td>{Math.round(item.confidence * 100)}%</td><td>{item.door_state}</td></tr>)}</tbody></table> : <Empty title="Chưa có lịch sử nhận diện" /> : null}{tab === 'alerts' ? alerts?.items.length ? <table><thead><tr><th>Thời gian</th><th>Mức độ</th><th>Tiêu đề</th><th>Nội dung</th><th>Trạng thái</th></tr></thead><tbody>{alerts.items.map((item) => <tr key={item.id}><td>{formatTime(item.created_at, true)}</td><td><Badge tone={item.severity === 'CRITICAL' ? 'danger' : item.severity === 'WARNING' ? 'warning' : 'info'}>{item.severity}</Badge></td><td>{item.title}</td><td>{item.message}</td><td>{item.is_read ? 'Đã đọc' : 'Chưa đọc'}</td></tr>)}</tbody></table> : <Empty title="Chưa có cảnh báo" /> : null}</div></Panel>
    <div className="history-footnote"><Activity size={16} /> Thời gian được hiển thị theo múi giờ của trình duyệt.</div>
  </div>
}
