import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, apiError, WS_URL } from './api'
import { useToast } from './ToastContext'
import type { AlertsResponse, CameraState, Cluster1State, Cluster2State, ClusterId, CommandResponse, Mode, Nodes, SensorLatest, Snapshot, SocketEvent } from './types'

type NodeState = Cluster1State | Cluster2State | CameraState
type PendingStatus = 'waiting' | 'timeout' | 'failed'
interface ExpectedState { mode?: Mode; outputs?: Record<string, boolean>; door_state?: string }
export interface PendingCommand {
  id: string | null
  status: PendingStatus
  frozen: NodeState
  expected: ExpectedState
  error?: string
}

interface LiveValue {
  snapshot: Snapshot | null
  latest: SensorLatest | null
  alerts: AlertsResponse | null
  socketStatus: 'connecting' | 'connected' | 'disconnected'
  apiOnline: boolean
  lastUpdated: Date | null
  pending: Partial<Record<ClusterId, PendingCommand>>
  nodeView: <K extends ClusterId>(id: K) => Nodes[K] | null
  refresh: () => Promise<void>
  sendCommand: (cluster: ClusterId, endpoint: string, body: Record<string, unknown>, expected: ExpectedState) => Promise<void>
}

const LiveContext = createContext<LiveValue | null>(null)

function matchesExpected(node: NodeState, expected: ExpectedState): boolean {
  if (expected.mode && 'mode' in node && node.mode !== expected.mode) return false
  if (expected.door_state && 'door_state' in node && node.door_state !== expected.door_state) return false
  if (expected.outputs) {
    if (!('outputs' in node)) return false
    for (const [key, value] of Object.entries(expected.outputs)) {
      if ((node.outputs as Record<string, boolean>)[key] !== value) return false
    }
  }
  return true
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [latest, setLatest] = useState<SensorLatest | null>(null)
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null)
  const [socketStatus, setSocketStatus] = useState<LiveValue['socketStatus']>('connecting')
  const [apiOnline, setApiOnline] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [pending, setPending] = useState<LiveValue['pending']>({})
  const snapshotRef = useRef<Snapshot | null>(null)
  const pendingRef = useRef<LiveValue['pending']>({})
  const notify = useToast()
  const notifyRef = useRef(notify)
  notifyRef.current = notify

  const updatePending = useCallback((next: LiveValue['pending']) => {
    pendingRef.current = next
    setPending(next)
  }, [])

  const applySnapshot = useCallback((next: Snapshot, sourceTopic?: string) => {
    snapshotRef.current = next
    setSnapshot(next)
    setApiOnline(true)
    setLastUpdated(new Date())

    for (const cluster of ['esp32_cluster1', 'esp32_cluster2', 'esp32_cam_01'] as const) {
      const entry = pendingRef.current[cluster]
      if (!entry) continue
      const node = next.nodes[cluster]
      const ack = node.last_ack
      if (entry.id && ack?.command_id === entry.id) {
        const copy = { ...pendingRef.current }
        if (ack.success === false) {
          copy[cluster] = { ...entry, id: null, status: 'failed', error: ack.error || 'Thiết bị từ chối lệnh.' }
          notifyRef.current(`Lệnh tới ${cluster} thất bại: ${ack.error || 'không có ACK thành công'}`, 'error')
        } else {
          delete copy[cluster]
          notifyRef.current('Thiết bị đã xác nhận lệnh.', 'success')
        }
        updatePending(copy)
      } else if (sourceTopic?.includes(`/device/${cluster === 'esp32_cluster1' ? 'cluster1' : cluster === 'esp32_cluster2' ? 'cluster2' : 'cam'}/status`) && matchesExpected(node, entry.expected)) {
        const copy = { ...pendingRef.current }
        delete copy[cluster]
        updatePending(copy)
        notifyRef.current('Đã nhận trạng thái thực tế từ thiết bị.', 'success')
      }
    }
  }, [updatePending])

  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([
      api.get<Snapshot>('/api/mqtt/state'),
      api.get<SensorLatest>('/api/sensors/latest'),
      api.get<AlertsResponse>('/api/alerts?limit=8'),
    ])
    if (results[0].status === 'fulfilled') applySnapshot(results[0].value.data)
    else setApiOnline(false)
    if (results[1].status === 'fulfilled') setLatest(results[1].value.data)
    if (results[2].status === 'fulfilled') setAlerts(results[2].value.data)
  }, [applySnapshot])

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => { void refresh() }, 10000)
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let closed = false
    let attempts = 0

    function connect() {
      if (closed) return
      setSocketStatus('connecting')
      try {
        socket = new WebSocket(WS_URL)
        socket.onopen = () => { attempts = 0; setSocketStatus('connected') }
        socket.onmessage = (message) => {
          try {
            const event = JSON.parse(message.data) as SocketEvent
            const data = event.data as Record<string, unknown>
            if (event.event === 'INITIAL_STATE' && data.nodes) {
              applySnapshot({ mqtt_connected: Boolean(data.mqtt_connected), owner_face_enrolled: Boolean(data.owner_face_enrolled), nodes: data.nodes as unknown as Nodes })
            } else if (event.event === 'MQTT_MESSAGE' && data.nodes) {
              const previous = snapshotRef.current
              applySnapshot({ mqtt_connected: previous?.mqtt_connected ?? true, owner_face_enrolled: previous?.owner_face_enrolled ?? false, broker: previous?.broker, nodes: data.nodes as unknown as Nodes }, String(data.topic || ''))
            } else if (event.event === 'FACE_RECOGNITION' && data.nodes) {
              const previous = snapshotRef.current
              applySnapshot({ mqtt_connected: previous?.mqtt_connected ?? true, owner_face_enrolled: previous?.owner_face_enrolled ?? false, nodes: data.nodes as unknown as Nodes })
            } else if (event.event === 'MQTT_STATUS') {
              setSnapshot((current) => {
                const next = current ? { ...current, mqtt_connected: Boolean(data.connected) } : current
                snapshotRef.current = next
                return next
              })
            } else if (event.event === 'OWNER_ENROLLED') {
              setSnapshot((current) => current ? { ...current, owner_face_enrolled: true } : current)
            } else if (event.event === 'NEW_ALERT') {
              void api.get<AlertsResponse>('/api/alerts?limit=8').then(({ data: result }) => setAlerts(result))
            }
          } catch { /* Ignore malformed events and continue polling. */ }
        }
        socket.onclose = () => {
          setSocketStatus('disconnected')
          if (!closed) reconnectTimer = window.setTimeout(connect, Math.min(15000, 1500 * 2 ** attempts++))
        }
        socket.onerror = () => socket?.close()
      } catch {
        setSocketStatus('disconnected')
        reconnectTimer = window.setTimeout(connect, 5000)
      }
    }
    connect()
    return () => {
      closed = true
      window.clearInterval(interval)
      window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [applySnapshot, refresh])

  const nodeView = useCallback(<K extends ClusterId>(id: K): Nodes[K] | null => {
    const held = pending[id]
    if (held) return held.frozen as Nodes[K]
    return snapshot?.nodes[id] ?? null
  }, [pending, snapshot])

  const sendCommand = useCallback(async (cluster: ClusterId, endpoint: string, body: Record<string, unknown>, expected: ExpectedState) => {
    if (pendingRef.current[cluster]?.status === 'waiting') throw new Error('Đang chờ thiết bị xác nhận lệnh trước.')
    const frozen = snapshotRef.current?.nodes[cluster]
    if (!frozen) throw new Error('Chưa có trạng thái thiết bị. Hãy tải lại dữ liệu.')
    updatePending({ ...pendingRef.current, [cluster]: { id: null, status: 'waiting', frozen, expected } })
    try {
      const { data } = await api.post<CommandResponse>(endpoint, body)
      const id = data.command.command_id
      updatePending({ ...pendingRef.current, [cluster]: { id, status: 'waiting', frozen, expected } })
      const current = snapshotRef.current
      if (current) applySnapshot(current)
      window.setTimeout(() => {
        const waiting = pendingRef.current[cluster]
        if (waiting?.id !== id || waiting.status !== 'waiting') return
        updatePending({ ...pendingRef.current, [cluster]: { ...waiting, status: 'timeout', error: 'Chưa có ACK sau 12 giây. Trạng thái chưa được xác nhận.' } })
        notifyRef.current('Chưa nhận ACK từ thiết bị. Trạng thái chưa được xác nhận.', 'error')
      }, 12000)
    } catch (error) {
      const copy = { ...pendingRef.current }
      delete copy[cluster]
      updatePending(copy)
      throw new Error(apiError(error))
    }
  }, [applySnapshot, updatePending])

  return <LiveContext.Provider value={{ snapshot, latest, alerts, socketStatus, apiOnline, lastUpdated, pending, nodeView, refresh, sendCommand }}>{children}</LiveContext.Provider>
}

export function useLive() {
  const value = useContext(LiveContext)
  if (!value) throw new Error('LiveProvider is missing')
  return value
}
