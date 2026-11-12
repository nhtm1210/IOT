export type Role = 'ADMIN' | 'USER' | 'GUEST'
export type Mode = 'AUTO' | 'MANUAL'
export type ClusterId = 'esp32_cluster1' | 'esp32_cluster2' | 'esp32_cam_01'

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
  is_active: boolean
  created_at: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface DeviceAck {
  command_id?: string
  success?: boolean
  error?: string | null
  mode?: Mode
  outputs?: Record<string, boolean>
  door_state?: string
}

export interface Cluster1State {
  online: boolean
  mode: Mode
  pir: boolean
  outputs: { light: boolean; buzzer: boolean }
  last_motion_event: Record<string, unknown> | null
  last_ack: DeviceAck | null
  updated_at: string | null
}

export interface Cluster2State {
  online: boolean
  mode: Mode
  temperature_c: number | null
  humidity_pct: number | null
  light_adc: number | null
  light_lux: number | null
  is_dark: boolean | null
  outputs: { light: boolean; fan: boolean }
  last_ack: DeviceAck | null
  updated_at: string | null
}

export interface CameraState {
  online: boolean
  camera_ready: boolean
  door_state: 'OPEN' | 'LOCKED'
  servo_angle_deg: number
  last_identity: 'KNOWN' | 'UNKNOWN' | 'NO_FACE' | 'NONE'
  last_person_name: string | null
  last_confidence: number | null
  last_image_url: string | null
  last_recognition: Record<string, unknown> | null
  last_ack: DeviceAck | null
  updated_at: string | null
}

export interface Nodes {
  esp32_cluster1: Cluster1State
  esp32_cluster2: Cluster2State
  esp32_cam_01: CameraState
}

export interface Snapshot {
  mqtt_connected: boolean
  broker?: string
  owner_face_enrolled: boolean
  nodes: Nodes
}

export interface SensorLatest {
  mqtt_connected: boolean
  summary: {
    temperature_c: number | null
    humidity_pct: number | null
    light_adc: number | null
    light_lux: number | null
    is_dark: boolean | null
    pir_motion: boolean
    door_state: string
    servo_angle_deg: number
  }
  nodes: Nodes
}

export interface SensorHistory {
  id: number
  cluster_id: string
  temperature_c: number | null
  humidity_pct: number | null
  light_adc: number | null
  light_lux: number | null
  is_dark: boolean | null
  pir: boolean | null
  light_state: boolean | null
  fan_state: boolean | null
  buzzer_state: boolean | null
  created_at: string
}

export interface DeviceHistory {
  id: number
  command_id: string
  cluster_id: string
  device_id: string
  action: string
  state: string
  mode: string
  triggered_by: string
  ack_received: boolean
  success: boolean
  error: string | null
  created_at: string
}

export interface Alert {
  id: number
  alert_type: string
  severity: 'INFO' | 'WARNING' | 'CRITICAL'
  cluster_id: string
  title: string
  message: string
  is_read: boolean
  telegram_sent: boolean
  image_url: string | null
  created_at: string
}

export interface AlertsResponse {
  unread_count: number
  count: number
  items: Alert[]
}

export interface Recognition {
  id: number
  event_id: string
  command_id: string | null
  device_id: string
  identity: 'KNOWN' | 'UNKNOWN' | 'NO_FACE'
  person_name: string
  confidence: number
  authorized: boolean
  door_action: string
  door_state: string
  servo_angle_deg: number
  image_url: string | null
  created_at: string
}

export interface AutomationRule {
  id: number
  code: string
  name: string
  cluster_id: ClusterId
  description: string
  is_enabled: boolean
  config: Record<string, string | number | boolean | null>
  updated_at: string
}

export interface Settings {
  temp_threshold_c: number
  humidity_threshold_pct: number
  light_adc_threshold: number
  pir_hold_seconds: number
  face_match_threshold: number
  door_open_seconds: number
  security_armed: boolean
  telegram_enabled: boolean
  telegram_bot_token: string
  telegram_chat_id: string
}

export interface Device {
  id: string
  cluster_id: ClusterId
  name: string
  device_type: string
  gpio_pin: number
  state: string
  mode: Mode
  online: boolean
  updated_at: string
}

export interface CommandResponse {
  status: 'published'
  command: { command_id: string; mode?: Mode; outputs?: Record<string, boolean> }
  node?: Cluster1State | Cluster2State | CameraState
}

export interface SocketEvent {
  event: string
  timestamp?: string
  data: unknown
}
