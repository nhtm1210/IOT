# TÀI LIỆU ĐẶC TẢ API & HƯỚNG DẪN TÍCH HỢP DÀNH CHO FRONTEND (API_SPEC.md)

> **Dự án:** Hệ thống Nhà thông minh IoT tích hợp AI nhận diện khuôn mặt mở cửa Servo SG90  
> **Người bàn giao:** Thành viên 2 (Backend Developer)  
> **Người nhận bàn giao:** Thành viên 3 (Frontend Developer - React + Vite + TypeScript + Tailwind CSS)  
> **Base URL (Local/LAN):** `http://localhost:8000` (hoặc `http://<IP_LAN_BACKEND>:8000`)  
> **Swagger UI (Test trực tiếp trên trình duyệt):** `http://localhost:8000/docs`  
> **WebSocket Real-time URL:** `ws://localhost:8000/ws/dashboard`

---

## 1. Khởi chạy Backend & Giả lập mạch ESP32 trong 30 giây (Dành cho Frontend)

Khi phát triển giao diện React, bạn **không cần cắm mạch ESP32 thật** mà vẫn có đầy đủ dữ liệu nhiệt độ, độ ẩm, ánh sáng nhảy mỗi 2 giây và sự kiện PIR chuyển động mỗi 12 giây:

### Bước 1: Mở Terminal 1 — Chạy Backend Server (cổng `8000` + MQTT Broker cổng `1883`)
```powershell
cd backend
pip install -r requirements.txt
python run.py
```
- Mở trình duyệt kiểm tra Swagger UI tại: **`http://localhost:8000/docs`**

### Bước 2: Mở Terminal 2 — Chạy bộ giả lập 3 cụm ESP32 (`simulator_esp32.py`)
```powershell
cd mqtt-sample
python simulator_esp32.py
```

---

## 2. Tài khoản Mặc định & Cơ chế Xác thực (JWT + RBAC)

Khi Backend khởi chạy lần đầu, cơ sở dữ liệu SQLite (`backend/data/smarthome.db`) tự động tạo sẵn **3 tài khoản mặc định**:

| Username | Password | Role | Quyền hạn trên hệ thống |
|---|---|---|---|
| `admin` | `admin123` | `ADMIN` | Toàn quyền: Điều khiển 3 cụm, Mở khóa cửa SG90, Lưu mặt chủ nhà, Sửa kịch bản tự động, Quản lý Users & Telegram. |
| `user` | `user123` | `USER` | Thành viên gia đình: Xem Dashboard, Bật/tắt đèn/quạt/còi, Chuyển `AUTO`/`MANUAL`, Xem lịch sử. |
| `guest` | `guest123` | `GUEST` | Khách tham quan: **Chỉ xem (Read-Only)**. Nếu gọi API điều khiển thiết bị sẽ nhận lỗi `403 Forbidden`. |

### Cách gửi JWT Token từ Frontend:
Sau khi gọi `POST /api/auth/login` và nhận được `access_token`, gắn vào Header của mọi request tiếp theo:
```http
Authorization: Bearer <access_token>
```

---

## 3. Danh mục Tổng hợp 24 REST API Endpoints

### 3.1. Nhóm 1 — Xác thực & Người dùng (`Auth & Users`)

#### 1) `POST /api/auth/login` — Đăng nhập
- **Request Body (`application/json`):**
```json
{
  "username": "admin",
  "password": "admin123"
}
```
- **Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": 1,
    "username": "admin",
    "full_name": "Quản trị viên (Chủ nhà)",
    "role": "ADMIN",
    "is_active": true,
    "created_at": "2026-11-10T02:00:00Z"
  }
}
```

#### 2) `GET /api/auth/me` — Lấy thông tin người dùng hiện tại
- **Headers:** `Authorization: Bearer <access_token>`
- **Response `200 OK`:** Trả về object `user` giống trên. Nếu token hết hạn hoặc chưa đăng nhập trả về `401 Unauthorized`.

#### 3) Quản lý tài khoản (Dành cho trang Quản lý người dùng của `ADMIN`):
- `GET /api/users`: Lấy danh sách toàn bộ người dùng.
- `POST /api/users`: Tạo người dùng mới (`{"username": "...", "password": "...", "full_name": "...", "role": "USER"}`).
- `PUT /api/users/{user_id}`: Cập nhật `full_name`, `role`, `is_active`, hoặc đổi `password`.
- `DELETE /api/users/{user_id}`: Xóa người dùng.

---

### 3.2. Nhóm 2 — Trạng thái & Điều khiển trực tiếp 3 cụm ESP32 (`Dashboard Page`)

#### 1) `GET /api/mqtt/state` — Lấy toàn bộ trạng thái thời gian thực của 3 cụm ESP32
- **Response `200 OK`:**
```json
{
  "mqtt_connected": true,
  "broker": "127.0.0.1:1883",
  "owner_face_enrolled": true,
  "nodes": {
    "esp32_cluster1": {
      "online": true,
      "mode": "AUTO",
      "pir": false,
      "outputs": {
        "light": false,
        "buzzer": false
      },
      "last_motion_event": null,
      "last_ack": null,
      "updated_at": "2026-11-10T02:10:00Z"
    },
    "esp32_cluster2": {
      "online": true,
      "mode": "AUTO",
      "temperature_c": 31.5,
      "humidity_pct": 36.5,
      "light_adc": 1400,
      "light_lux": 18.0,
      "is_dark": true,
      "outputs": {
        "light": true,
        "fan": true
      },
      "last_ack": null,
      "updated_at": "2026-11-10T02:10:02Z"
    },
    "esp32_cam_01": {
      "online": true,
      "camera_ready": true,
      "door_state": "LOCKED",
      "servo_angle_deg": 0,
      "last_identity": "KNOWN",
      "last_person_name": "Chu_Nha",
      "last_confidence": 0.94,
      "last_image_url": "/api/security/images/cam_evt_173120000.jpg",
      "last_recognition": null,
      "last_ack": null,
      "updated_at": "2026-11-10T02:09:50Z"
    }
  }
}
```

#### 2) `POST /api/mqtt/cluster1/control` — Điều khiển Cụm ESP 1 (PIR + Đèn GPIO26 + Còi GPIO25)
- **Ví dụ bật Đèn, tắt Còi ở chế độ Thủ công (`MANUAL`):**
```json
{
  "mode": "MANUAL",
  "light": true,
  "buzzer": false
}
```
- **Ví dụ chuyển Cụm 1 về chế độ Tự động (`AUTO`):**
```json
{
  "mode": "AUTO"
}
```

#### 3) `POST /api/mqtt/cluster2/control` — Điều khiển Cụm ESP 2 (DHT22 + LDR + Đèn GPIO2 + Quạt GPIO5)
- **Ví dụ bật Quạt, tắt Đèn ở chế độ Thủ công (`MANUAL`):**
```json
{
  "mode": "MANUAL",
  "light": false,
  "fan": true
}
```
- **Ví dụ chuyển Cụm 2 về chế độ Tự động (`AUTO`):**
```json
{
  "mode": "AUTO"
}
```

#### 4) `POST /api/mqtt/cam/door` — Mở / Khóa cửa Servo SG90 từ giao diện Web
- **Mở cửa khẩn cấp (Quay Servo SG90 lên góc $90^\circ$ trong 5 giây):**
```json
{
  "identity": "KNOWN",
  "authorized": true,
  "person_name": "Admin",
  "confidence": 1.0
}
```
- **Khóa cửa ngay lập tức (Đưa Servo SG90 về góc $0^\circ$):**
```json
{
  "identity": "UNKNOWN",
  "authorized": false,
  "person_name": "Admin",
  "confidence": 0.0
}
```

#### 5) `POST /api/mqtt/cam/capture` — Yêu cầu ESP32-CAM chụp ảnh & nhận diện ngay
- **Body:** *(Không cần body)*
- **Response:** `{"status": "published", "command": {"action": "CAPTURE", ...}}`

---

### 3.3. Nhóm 3 — Cảm biến & Biểu đồ Thống kê (`Sensors & Recharts`)

#### 1) `GET /api/sensors/latest` — Dữ liệu tóm tắt cho 4 thẻ đầu trang Dashboard
- **Response `200 OK`:**
```json
{
  "mqtt_connected": true,
  "summary": {
    "temperature_c": 31.5,
    "humidity_pct": 36.5,
    "light_adc": 1400,
    "light_lux": 18.0,
    "is_dark": true,
    "pir_motion": false,
    "door_state": "LOCKED",
    "servo_angle_deg": 0
  },
  "nodes": { ... }
}
```

#### 2) `GET /api/sensors/history` — Dữ liệu chuỗi thời gian vẽ biểu đồ Recharts
- **Query Params:**
  - `cluster_id`: `esp32_cluster2` (mặc định) hoặc `esp32_cluster1` hoặc `all`
  - `limit`: Số điểm dữ liệu (mặc định `60`, tối đa `500`)
  - `minutes`: Lọc trong $N$ phút gần nhất (tùy chọn)
- **Response `200 OK` (Đã sắp xếp sẵn từ cũ $\rightarrow$ mới để truyền thẳng vào `<LineChart data={history}>`):**
```json
[
  {
    "id": 1,
    "cluster_id": "esp32_cluster2",
    "temperature_c": 30.2,
    "humidity_pct": 39.5,
    "light_adc": 1800,
    "light_lux": 35.0,
    "is_dark": true,
    "pir": false,
    "light_state": true,
    "fan_state": true,
    "buzzer_state": false,
    "created_at": "2026-11-10T02:00:00Z"
  }
]
```

---

### 3.4. Nhóm 4 — Thiết bị & Nhật ký Điều khiển (`Devices & Control History`)

- **`GET /api/devices`**: Trả về mảng 5 thiết bị (`light_1`, `buzzer_1`, `light_2`, `fan_1`, `door_servo_1`) kèm trạng thái `ON`/`OFF`/`OPEN`/`LOCKED`, chân `gpio_pin`, `mode` và `online`.
- **`POST /api/devices/control`**: Điều khiển thiết bị theo `device_id` đơn lẻ:
  ```json
  {
    "device_id": "fan_1",
    "state": "ON",
    "mode": "MANUAL"
  }
  ```
- **`GET /api/devices/history?limit=50`**: Lịch sử các lệnh điều khiển đã gửi và trạng thái xác nhận `ack_received`.

---

### 3.5. Nhóm 5 — An ninh Camera AI & Cửa Servo SG90 (`Security AI Page`)

1. **`GET /api/recognitions?limit=30`**: Lấy danh sách lịch sử nhận diện khuôn mặt & đóng/mở cửa:
   ```json
   [
     {
       "id": 1,
       "event_id": "cam_evt_173120001",
       "command_id": "access_9a8b7c6d",
       "device_id": "esp32_cam_01",
       "identity": "KNOWN",
       "person_name": "Chu_Nha",
       "confidence": 0.94,
       "authorized": true,
       "door_action": "OPEN",
       "door_state": "OPEN",
       "servo_angle_deg": 90,
       "image_url": "/api/security/images/cam_evt_173120001.jpg",
       "created_at": "2026-11-10T02:12:00Z"
     }
   ]
   ```
   > **Hiển thị ảnh trên Frontend:** Ghép `http://localhost:8000` + `item.image_url` vào thẻ `<img src={...} />`.
2. **`GET /api/security/owner-face`**: Trả về ảnh JPEG mẫu mặt chủ nhà hiện tại (`<img src="http://localhost:8000/api/security/owner-face" />`).
3. **`POST /api/security/enroll`**: Cho phép người dùng upload file ảnh mẫu mặt chủ nhà từ máy tính hoặc chụp từ Webcam trên Web (`multipart/form-data` với field `file`, hoặc raw bytes `image/jpeg`).
4. **`POST /api/security/recognize`**: Gửi ảnh JPEG để nhận diện thử ngay từ giao diện Web (hoặc từ ESP32-CAM) và kích hoạt Servo SG90.

---

### 3.6. Nhóm 6 — Kịch bản Tự động hóa (`Automation Rules Page`)

- **`GET /api/automation/rules`**: Trả về 4 kịch bản tự động hóa chuẩn của 3 cụm ESP32:
  1. `RULE_C1_PIR_ALARM`: Cụm 1 — Phát hiện chuyển động PIR bật Còi & Đèn (`hold_seconds: 5`).
  2. `RULE_C2_TEMP_HUM_FAN`: Cụm 2 — Nhiệt độ $\ge 30^\circ\text{C}$ & Độ ẩm $\le 40\%$ bật Quạt.
  3. `RULE_C2_LIGHT_LDR`: Cụm 2 — Trời tối (`light_adc_threshold: 2000`) bật Đèn.
  4. `RULE_CAM_FACE_DOOR`: ESP32-CAM — Khớp mặt chủ nhà (`confidence_threshold: 0.65`) quay Servo SG90 góc $90^\circ$ mở cửa 5s.
- **`PUT /api/automation/rules/{rule_id}`**: Bật/tắt kịch bản hoặc thay đổi thông số ngưỡng:
  ```json
  {
    "is_enabled": true,
    "config": {
      "temp_threshold_c": 29.5,
      "humidity_max_pct": 42.0
    }
  }
  ```

---

### 3.7. Nhóm 7 — Cảnh báo, Cài đặt & Telegram Bot (`Alerts & Settings`)

- **`GET /api/alerts?limit=50`**: Trả về `{ "unread_count": 2, "count": 10, "items": [...] }`.
- **`PUT /api/alerts/{alert_id}/read`**: Đánh dấu 1 cảnh báo đã đọc.
- **`POST /api/alerts/read-all`**: Đánh dấu tất cả cảnh báo đã đọc.
- **`GET /api/settings`** & **`PUT /api/settings`**: Lấy và cập nhật toàn bộ cài đặt ngưỡng & Telegram Bot:
  ```json
  {
    "temp_threshold_c": 30.0,
    "humidity_threshold_pct": 40.0,
    "light_adc_threshold": 2000,
    "pir_hold_seconds": 5,
    "face_match_threshold": 0.65,
    "door_open_seconds": 5,
    "security_armed": true,
    "telegram_enabled": false,
    "telegram_bot_token": "",
    "telegram_chat_id": ""
  }
  ```
- **`POST /api/settings/telegram/test`**: Gửi tin nhắn kiểm tra tới Telegram Bot.

---

## 4. Kết nối Real-time WebSocket (`/ws/dashboard`)

Thay vì phải gọi API liên tục (polling), Frontend chỉ cần mở kết nối WebSocket tới `ws://localhost:8000/ws/dashboard`.

### Các sự kiện Server đẩy xuống:
- `INITIAL_STATE`: Gửi ngay khi vừa kết nối thành công, chứa toàn bộ trạng thái 3 cụm ESP32.
- `MQTT_MESSAGE`: Gửi mỗi khi có bất kỳ bản tin cảm biến, chuyển động PIR, trạng thái hoặc ACK mới từ 3 cụm ESP32 (`data.nodes` chứa snapshot mới nhất).
- `FACE_RECOGNITION`: Gửi ngay khi có kết quả nhận diện khuôn mặt và lệnh đóng/mở cửa Servo SG90.
- `NEW_ALERT`: Gửi ngay khi có cảnh báo mới (người lạ `UNKNOWN`, chuyển động `MOTION_DETECTED`, nhiệt độ vượt ngưỡng) — Frontend có thể dùng để bật Toast Notification và tăng số đếm trên biểu tượng chuông 🔔.

---

## 5. Bộ Code Mẫu TypeScript Copy-Paste cho Thành viên 3 (`frontend/src/`)

### 5.1. File `src/api/axiosClient.ts`
```typescript
import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

const axiosClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

axiosClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("smarthome_token");
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default axiosClient;
```

### 5.2. File `src/api/smarthomeApi.ts`
```typescript
import axiosClient, { API_BASE_URL } from "./axiosClient";

export const smarthomeApi = {
  // 1. Auth
  login: async (username: string, password: string) => {
    const res = await axiosClient.post("/api/auth/login", { username, password });
    localStorage.setItem("smarthome_token", res.data.access_token);
    return res.data;
  },
  getMe: () => axiosClient.get("/api/auth/me").then((r) => r.data),

  // 2. Trạng thái & Điều khiển 3 cụm ESP32
  getMqttState: () => axiosClient.get("/api/mqtt/state").then((r) => r.data),
  getMqttLogs: (limit = 50) =>
    axiosClient.get(`/api/mqtt/logs?limit=${limit}`).then((r) => r.data),

  controlCluster1: (payload: {
    mode: "AUTO" | "MANUAL";
    light?: boolean;
    buzzer?: boolean;
  }) => axiosClient.post("/api/mqtt/cluster1/control", payload).then((r) => r.data),

  controlCluster2: (payload: {
    mode: "AUTO" | "MANUAL";
    light?: boolean;
    fan?: boolean;
  }) => axiosClient.post("/api/mqtt/cluster2/control", payload).then((r) => r.data),

  controlCamDoor: (open: boolean, personName = "Admin") =>
    axiosClient
      .post("/api/mqtt/cam/door", {
        identity: open ? "KNOWN" : "UNKNOWN",
        authorized: open,
        person_name: personName,
        confidence: open ? 1.0 : 0.0,
      })
      .then((r) => r.data),

  triggerCamCapture: () =>
    axiosClient.post("/api/mqtt/cam/capture").then((r) => r.data),

  // 3. Cảm biến & Biểu đồ Recharts
  getLatestSensors: () =>
    axiosClient.get("/api/sensors/latest").then((r) => r.data),
  getSensorHistory: (clusterId = "esp32_cluster2", limit = 60) =>
    axiosClient
      .get(`/api/sensors/history?cluster_id=${clusterId}&limit=${limit}`)
      .then((r) => r.data),

  // 4. Thiết bị & Lịch sử điều khiển
  getDevices: () => axiosClient.get("/api/devices").then((r) => r.data),
  getDeviceHistory: (limit = 50) =>
    axiosClient.get(`/api/devices/history?limit=${limit}`).then((r) => r.data),

  // 5. Nhận diện khuôn mặt AI & Mở cửa SG90
  getRecognitions: (limit = 30) =>
    axiosClient.get(`/api/recognitions?limit=${limit}`).then((r) => r.data),
  enrollOwnerFace: (file: File | Blob, personName = "Chu_Nha") => {
    const formData = new FormData();
    formData.append("file", file);
    return axiosClient
      .post(`/api/security/enroll?person_name=${encodeURIComponent(personName)}`, formData)
      .then((r) => r.data);
  },
  recognizeFaceFile: (file: File | Blob) => {
    const formData = new FormData();
    formData.append("file", file);
    return axiosClient.post("/api/security/recognize", formData).then((r) => r.data);
  },
  getOwnerFaceUrl: () => `${API_BASE_URL}/api/security/owner-face?t=${Date.now()}`,
  resolveImageUrl: (path: string | null) =>
    path ? (path.startsWith("http") ? path : `${API_BASE_URL}${path}`) : null,

  // 6. Kịch bản Tự động hóa
  getAutomationRules: () =>
    axiosClient.get("/api/automation/rules").then((r) => r.data),
  updateAutomationRule: (
    ruleId: number,
    payload: { is_enabled?: boolean; config?: Record<string, unknown> }
  ) => axiosClient.put(`/api/automation/rules/${ruleId}`, payload).then((r) => r.data),

  // 7. Cảnh báo & Cài đặt
  getAlerts: (limit = 50) =>
    axiosClient.get(`/api/alerts?limit=${limit}`).then((r) => r.data),
  markAlertRead: (alertId: number) =>
    axiosClient.put(`/api/alerts/${alertId}/read`).then((r) => r.data),
  markAllAlertsRead: () =>
    axiosClient.post("/api/alerts/read-all").then((r) => r.data),
  getSettings: () => axiosClient.get("/api/settings").then((r) => r.data),
  updateSettings: (payload: Record<string, unknown>) =>
    axiosClient.put("/api/settings", payload).then((r) => r.data),
  testTelegram: (message?: string) =>
    axiosClient.post("/api/settings/telegram/test", { message }).then((r) => r.data),
};
```

---

## 6. Hướng dẫn Đóng gói Gộp chung FE + BE khi đi Báo cáo / Demo

1. Trong quá trình code giao diện: chạy `npm run dev` trong thư mục `frontend/` (cổng `5173`).
2. Khi chuẩn bị đi báo cáo hội đồng:
   ```powershell
   cd frontend
   npm run build
   ```
   Lệnh trên sẽ tạo thư mục `frontend/dist/`.
3. Khi chạy `python backend/run.py`, Backend sẽ tự động phát hiện thư mục `frontend/dist/` và phục vụ toàn bộ giao diện React ngay tại địa chỉ `http://localhost:8000` (cùng cổng với API và WebSocket).
