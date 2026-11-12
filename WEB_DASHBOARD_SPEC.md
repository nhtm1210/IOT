# ĐẶC TẢ & BỘ KHUNG GIAO DIỆN WEB DASHBOARD (FRONTEND SPECIFICATION)

> **Dự án:** Hệ thống Nhà thông minh IoT tích hợp AI nhận diện khuôn mặt  
> **Người nhận bàn giao:** Thành viên 3 (Frontend Developer) & Thành viên 2 (Backend Developer)  
> **Mục đích:** Quy định chi tiết danh sách tính năng, bố cục màn hình (Wireframes), cấu trúc thư mục React và bảng ánh xạ dữ liệu từ 3 cụm ESP32 lên giao diện Web.

---

## 1. Tổng quan công nghệ & Phong cách thiết kế (UI/UX Concept)

### 1.1. Công nghệ sử dụng
- **Framework:** React 18 + Vite + TypeScript
- **Styling:** Tailwind CSS + Lucide React (Icons)
- **Biểu đồ:** Recharts (LineChart, AreaChart)
- **Giao tiếp API:** Axios (gọi REST API tới Backend cổng `8000`)
- **Điều khiển giọng nói (Tùy chọn):** Web Speech API tích hợp sẵn trên trình duyệt Chrome/Edge

### 1.2. Quy ước màu sắc trạng thái (Status Indicators)
- 🟢 **Xanh lá (`emerald-500`):** Thiết bị đang Online / Khớp mặt chủ nhà (`KNOWN`) / Trạng thái an toàn.
- 🟡 **Vàng cam (`amber-500`):** Đang ở chế độ Thủ công (`MANUAL`) / Nhiệt độ cao cảnh báo.
- 🔴 **Đỏ (`rose-500` + hiệu ứng pulse):** Phát hiện chuyển động (`pir = true`) / Còi đang kêu / Người lạ (`UNKNOWN`).
- ⚪ **Xám (`slate-400`):** Thiết bị Offline / Cảm biến chưa đọc được (`null`) / Không có khuôn mặt (`NO_FACE`).

---

## 2. Cấu trúc thư mục `frontend/` đề xuất

```text
frontend/
├── public/
├── src/
│   ├── api/
│   │   ├── axiosClient.ts          # Cấu hình baseURL (http://localhost:8000) & JWT Token
│   │   └── smarthomeApi.ts         # Các hàm gọi API lấy trạng thái, gửi lệnh điều khiển 3 cụm
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx         # Thanh điều hướng bên trái
│   │   │   └── Header.tsx          # Thanh trạng thái MQTT, thông báo, giọng nói
│   │   ├── dashboard/
│   │   │   ├── SensorSummaryCards.tsx  # 4 thẻ thông số: Nhiệt độ, Độ ẩm, Ánh sáng, PIR
│   │   │   ├── Cluster1Card.tsx        # Khối điều khiển Cụm ESP 1 (PIR + Đèn + Còi)
│   │   │   ├── Cluster2Card.tsx        # Khối điều khiển Cụm ESP 2 (DHT22 + LDR + Đèn + Quạt)
│   │   │   └── CameraDoorCard.tsx      # Khối điều khiển ESP32-CAM & Cửa Servo SG90
│   ├── pages/
│   │   ├── LoginPage.tsx           # Màn hình đăng nhập
│   │   ├── DashboardPage.tsx       # Màn hình chính giám sát & điều khiển 3 cụm
│   │   ├── SecurityAiPage.tsx      # Màn hình Camera AI, lưu mặt chủ nhà & lịch sử mở cửa
│   │   ├── AutomationPage.tsx      # Màn hình cấu hình quy tắc tự động hóa
│   │   └── HistoryChartsPage.tsx   # Màn hình biểu đồ Recharts & nhật ký sự kiện
│   ├── types/
│   │   └── smarthome.ts            # Định nghĩa TypeScript Interfaces khớp với MQTT JSON
│   ├── App.tsx
│   └── main.tsx
├── package.json
└── tailwind.config.js
```

---

## 3. Các tính năng cốt lõi của Web Dashboard

1. **Giám sát thời gian thực 3 cụm ESP32:**
   - **Cụm ESP 1 (`esp32_cluster1`):** Trạng thái cảm biến chuyển động PIR (`CÓ CHUYỂN ĐỘNG` / `BÌNH THƯỜNG`), trạng thái Đèn cảnh báo (`GPIO 26`) và Còi Buzzer (`GPIO 25`).
   - **Cụm ESP 2 (`esp32_cluster2`):** Nhiệt độ ($^\circ\text{C}$), Độ ẩm ($\%$), Cường độ ánh sáng (`ADC` và `Lux`), trạng thái `Trời Tối` / `Trời Sáng`, trạng thái Đèn chiếu sáng (`GPIO 2`) và Quạt (`GPIO 5`).
   - **Cụm Camera AI (`esp32_cam_01`):** Hình ảnh chụp mới nhất, kết quả nhận diện (`KNOWN - Chủ nhà`, `UNKNOWN - Người lạ`, `NO_FACE - Không có mặt`), trạng thái cửa và góc quay **Servo SG90** (`OPEN - 90°` / `LOCKED - 0°`).

2. **Điều khiển thiết bị từ xa & Chuyển chế độ `AUTO` / `MANUAL`:**
   - Mỗi cụm có nút gạt chuyển đổi giữa:
     - **`AUTO` (Tự động):** Mạch ESP32 tự bật/tắt theo kịch bản cảm biến.
     - **`MANUAL` (Thủ công):** Người dùng tự bật/tắt từng thiết bị (Đèn, Quạt, Còi) trên giao diện Web; chế độ `AUTO` sẽ không tự ý ghi đè khi đang ở `MANUAL`.
   - Nút bấm hiển thị trạng thái `Loading...` khi vừa gửi lệnh và chỉ chuyển sang `BẬT`/`TẮT` sau khi nhận được xác nhận `ACK` từ ESP32.

3. **Nhận diện khuôn mặt chủ nhà & Kiểm soát cửa Servo SG90:**
   - Nút **"Lưu mặt chủ nhà (Enroll)"**: Chụp ảnh từ ESP32-CAM và lưu làm mẫu khuôn mặt chủ nhà trên Backend.
   - Nút **"Chụp ảnh & Nhận diện mở cửa"**: Chụp ảnh, đối chiếu với mặt chủ nhà đã lưu sẵn; nếu khớp (`KNOWN`) thì quay Servo SG90 góc $90^\circ$ mở cửa trong 5 giây, nếu không khớp thì giữ khóa ở $0^\circ$.
   - Nút **"Mở cửa khẩn cấp ($90^\circ$)"** và **"Khóa cửa ($0^\circ$)"** dành cho Admin trên Web.

4. **Biểu đồ thống kê & Nhật ký hoạt động:**
   - Biểu đồ đường (Line Chart) theo dõi biến thiên Nhiệt độ & Độ ẩm theo thời gian.
   - Biểu đồ vùng (Area Chart) theo dõi cường độ ánh sáng (`ADC` / `Lux`).
   - Bảng lịch sử phát hiện chuyển động, lịch sử nhận diện khuôn mặt và lịch sử bật/tắt thiết bị.

---

## 4. Phác thảo chi tiết các màn hình giao diện (Wireframes)

### 4.1. Màn hình 1: Trang chủ Dashboard Tổng quan (`/dashboard`)

```text
+--------------------------------------------------------------------------------------------------+
| 🏠 SMART HOME IoT AI     [🟢 MQTT: Đã kết nối]          [🎙️ Giọng nói] [🔔 Cảnh báo (2)] [👤 Admin] |
+------------------+-------------------------------------------------------------------------------+
| MENU ĐIỀU HƯỚNG  |  1. THÔNG SỐ MÔI TRƯỜNG & AN NINH THỜI GIAN THỰC                              |
|                  |  +------------------+ +------------------+ +------------------+ +-----------+ |
| 👉 [📊 Dashboard] |  | 🌡️ NHIỆT ĐỘ     | | 💧 ĐỘ ẨM        | | ☀️ ÁNH SÁNG     | | 🚨 PIR    | |
|    [📷 AI & Cửa] |  |     31.5 °C      | |      36.5 %      | |  1400 ADC (18lx) | | CÓ NGƯỜI! | |
|    [⚙️ Tự động]  |  | Cao (>= 30°C)    | | Thấp (<= 40%)    | | 🌙 Trời đang tối | | Cụm ESP 1 | |
|    [📈 Lịch sử]  |  +------------------+ +------------------+ +------------------+ +-----------+ |
|    [🔧 Cài đặt]  |                                                                               |
|                  |  2. BẢNG ĐIỀU KHIỂN 3 CỤM PHẦN CỨNG ESP32                                     |
|                  |  +------------------------------------+ +-----------------------------------+ |
|                  |  | 🛡️ CỤM ESP 1: BÁO ĐỘNG CHUYỂN ĐỘNG | | 🌿 CỤM ESP 2: MÔI TRƯỜNG & PHÒNG | |
|                  |  | Trạng thái: 🟢 Online              | | Trạng thái: 🟢 Online             | |
|                  |  | Chế độ: [🔘 AUTO  |  MANUAL ]      | | Chế độ: [🔘 AUTO  |  MANUAL ]     | |
|                  |  | ---------------------------------- | | --------------------------------- | |
|                  |  | 💡 Đèn Cụm 1 (GPIO26): [ BẬT 🟢 ] | | 💡 Đèn Phòng (GPIO2):  [ BẬT 🟢 ] | |
|                  |  | 🔔 Còi Buzzer (GPIO25):[ KÊU 🔴 ] | | 🌀 Quạt Mát (GPIO5):   [ BẬT 🟢 ] | |
|                  |  | (Tự tắt sau 5s khi hết chuyển động)| | (Quạt bật do Nhiệt cao & Ẩm thấp) | |
|                  |  +------------------------------------+ +-----------------------------------+ |
|                  |      Khi chọn MANUAL có thể bấm bật tắt ở chữ bật tắt                         |
|                  |  +--------------------------------------------------------------------------+ |
|                  |  | 📷 CỤM ESP32-CAM: NHẬN DIỆN CHỦ NHÀ & CỬA SERVO SG90 (GPIO13)           | |
|                  |  | +------------------------+  Trạng thái cửa: [ 🔓 ĐANG MỞ (Góc 90°) ]     | |
|                  |  | |                        |  Nhận diện cuối: 🟢 CHỦ NHÀ (KNOWN - 94%)     | |
|                  |  | |   [Ảnh chụp Camera     |  Cơ chế tự động: Tự quay về 0° khóa sau 5s    | |
|                  |  | |    mới nhất từ CAM]    |                                               | |
|                  |  | |                        |  [📸 Chụp & Nhận diện] [🔓 Mở cửa] [🔒 Khóa] | |
|                  |  | +------------------------+                                               | |
|                  |  +--------------------------------------------------------------------------+ |
+------------------+-------------------------------------------------------------------------------+
```

---

### 4.2. Màn hình 2: Trang An ninh Camera AI & Cửa Servo SG90 (`/security`)

```text
+--------------------------------------------------------------------------------------------------+
| 📷 AN NINH CAMERA AI & KIỂM SOÁT CỬA RA VÀO (ESP32-CAM + SERVO SG90)                             |
+------------------------------------------------+-------------------------------------------------+
| KHUNG HÌNH CHỤP TỪ ESP32-CAM                   | TRẠNG THÁI NHẬN DIỆN & ĐỘNG CƠ SERVO SG90       |
| +--------------------------------------------+ | +---------------------------------------------+ |
| |                                            | | | 👤 Mẫu mặt chủ nhà: [Đã lưu sẵn (owner.jpg)]| |
| |                                            | | | ------------------------------------------- | |
| |          [ HÌNH ẢNH TỪ ESP32-CAM ]         | | | Kết quả vừa chụp:   🟢 KHỚP CHỦ NHÀ (KNOWN) | |
| |                                            | | | Độ tương đồng:      92.5% (Ngưỡng >= 65%)   | |
| |                                            | | | Góc Servo SG90:     90° (ĐANG MỞ CỬA)       | |
| +--------------------------------------------+ | +---------------------------------------------+ |
| [📸 Chụp & Nhận diện ngay] [👤 Lưu mặt chủ nhà]| [🔓 Mở cửa thủ công (90°)] [🔒 Khóa cửa (0°)]   |
+------------------------------------------------+-------------------------------------------------+
| NHẬT KÝ NHẬN DIỆN & ĐÓNG/MỞ CỬA GẦN ĐÂY                                                          |
| +----------------+---------+--------------------+-------------+--------------+-----------------+ |
| | Thời gian      | Ảnh     | Phân loại Identity | Độ tin cậy  | Lệnh gửi CAM | Trạng thái SG90 | |
| +----------------+---------+--------------------+-------------+--------------+-----------------+ |
| | 22:15:10       | [Xem]   | 🟢 KNOWN (Chủ nhà) | 94.0%       | OPEN         | Quay 90° Mở cửa | |
| | 22:10:04       | [Xem]   | 🔴 UNKNOWN (Lạ)    | 41.2%       | KEEP_LOCKED  | Giữ khóa (0°)   | |
| | 22:02:30       | [Xem]   | ⚪ NO_FACE         | 0.0%        | KEEP_LOCKED  | Giữ khóa (0°)   | |
| +----------------+---------+--------------------+-------------+--------------+-----------------+ |
+--------------------------------------------------------------------------------------------------+
```

---

### 4.3. Màn hình 3: Trang Kịch bản Tự động hóa (`/automation`)

```text
+--------------------------------------------------------------------------------------------------+
| ⚙️ CẤU HÌNH KỊCH BẢN TỰ ĐỘNG HÓA (AUTOMATION RULES)                                              |
+--------------------------------------------------------------------------------------------------+
| 1. KỊCH BẢN CỤM ESP 1 — PHÁT HIỆN CHUYỂN ĐỘNG BẬT CÒI & ĐÈN                       [Đang BẬT 🟢] |
|    • Khi cảm biến chuyển động PIR (GPIO27) ghi nhận có người                                     |
|    • Tự động bật Đèn LED (GPIO26) và bật Còi Buzzer (GPIO25)                                     |
|    • Thời gian giữ đèn sáng và còi kêu sau khi hết chuyển động: [ 5 ] giây                       |
+--------------------------------------------------------------------------------------------------+
| 2. KỊCH BẢN CỤM ESP 2 — NHIỆT ĐỘ CAO & ĐỘ ẨM THẤP BẬT QUẠT                        [Đang BẬT 🟢] |
|    • Khi Nhiệt độ >= [ 30.0 ] °C  VÀ  Độ ẩm <= [ 40.0 ] %                                        |
|    • Tự động Bật Quạt (GPIO5); nếu không thỏa điều kiện thì Tắt Quạt                             |
+--------------------------------------------------------------------------------------------------+
| 3. KỊCH BẢN CỤM ESP 2 — CẢM BIẾN ÁNH SÁNG TỰ ĐỘNG BẬT/TẮT ĐÈN                     [Đang BẬT 🟢] |
|    • Khi Trời tối (Giá trị đọc LDR ADC < [ 2000 ] hoặc cường độ sáng < [ 50 ] Lux)               |
|    • Trời tối -> Tự động Bật Đèn (GPIO2) | Trời sáng -> Tự động Tắt Đèn (GPIO2)                  |
+--------------------------------------------------------------------------------------------------+
| 4. KỊCH BẢN ESP32-CAM — NHẬN DIỆN KHUÔN MẶT CHỦ NHÀ MỞ CỬA SERVO SG90             [Đang BẬT 🟢] |
|    • Khi ảnh chụp khớp với khuôn mặt chủ nhà đã lưu sẵn (Confidence >= [ 65 ] %)                 |
|    • Khớp (KNOWN) -> Quay Servo SG90 góc 90° mở cửa 5s | Không khớp -> Servo SG90 không quay (0°)|
+--------------------------------------------------------------------------------------------------+
```

---

### 4.4. Màn hình 4: Trang Biểu đồ & Lịch sử (`/history`)

```text
+--------------------------------------------------------------------------------------------------+
| 📈 BIỂU ĐỒ MÔI TRƯỜNG & LỊCH SỬ HOẠT ĐỘNG                                                       |
+------------------------------------------------+-------------------------------------------------+
| BIỂU ĐỒ NHIỆT ĐỘ (°C) & ĐỘ ẨM (%) - CỤM ESP 2  | BIỂU ĐỒ ÁNH SÁNG (ADC / LUX) - CỤM ESP 2       |
| +--------------------------------------------+ | +---------------------------------------------+ |
| | 40 |      *---*                            | | | 3000 | *---*                   *---*        | |
| | 30 | *---*     *---*  (Đường Nhiệt độ °C)  | | | 2000 |------\-----------------/---- Ngưỡng  | |
| | 20 |                 (Đường Độ ẩm %)       | | | 1000 |       *---*---*---*---* (Trời tối)   | |
| +----+---------------------------------------+ | +------+--------------------------------------+ |
|      22:00   22:05   22:10   22:15             |        22:00   22:05   22:10   22:15          |
+------------------------------------------------+-------------------------------------------------+
| NHẬT KÝ SỰ KIỆN & ĐIỀU KHIỂN THIẾT BỊ                                                            |
| +----------------+------------------+------------------------+---------------------------------+ |
| | Thời gian      | Cụm thiết bị     | Loại sự kiện           | Chi tiết                        | |
| +----------------+------------------+------------------------+---------------------------------+ |
| | 22:15:10       | esp32_cam_01     | FACE_RECOGNITION       | Khớp chủ nhà (94%) -> Mở SG90   | |
| | 22:15:08       | esp32_cluster1   | MOTION_DETECTED        | Phát hiện chuyển động -> Còi kêu| |
| | 22:14:00       | esp32_cluster2   | AUTO_CONTROL           | Trời tối (ADC=1400) -> Bật đèn  | |
| +----------------+------------------+------------------------+---------------------------------+ |
+--------------------------------------------------------------------------------------------------+
```

---

## 5. Định nghĩa TypeScript Interfaces mẫu cho Thành viên 3 (`src/types/smarthome.ts`)

Thành viên 3 có thể copy trực tiếp file dưới đây vào project React + TypeScript để khớp 100% với JSON từ `server_mqtt_sample.py` và Backend:

```typescript
export type ControlMode = "AUTO" | "MANUAL";
export type IdentityState = "KNOWN" | "UNKNOWN" | "NO_FACE" | "NONE";
export type DoorState = "OPEN" | "LOCKED";

export interface Cluster1State {
  online: boolean;
  mode: ControlMode;
  pir: boolean;
  outputs: {
    light: boolean;
    buzzer: boolean;
  };
  updated_at: string | null;
}

export interface Cluster2State {
  online: boolean;
  mode: ControlMode;
  temperature_c: number | null;
  humidity_pct: number | null;
  light_adc: number | null;
  light_lux: number | null;
  is_dark: boolean | null;
  outputs: {
    light: boolean;
    fan: boolean;
  };
  updated_at: string | null;
}

export interface Esp32CamState {
  online: boolean;
  camera_ready: boolean;
  door_state: DoorState;
  servo_angle_deg: number;
  last_identity: IdentityState;
  last_person_name: string | null;
  updated_at: string | null;
}

export interface SystemSnapshotResponse {
  mqtt_connected: boolean;
  broker: string;
  owner_face_enrolled: boolean;
  nodes: {
    esp32_cluster1: Cluster1State;
    esp32_cluster2: Cluster2State;
    esp32_cam_01: Esp32CamState;
  };
}
```

---

## 6. Bảng tổng hợp API Endpoints kết nối giữa Frontend và Backend

| Hành động trên giao diện Web | Method & Endpoint | Body JSON gửi lên |
|---|---|---|
| Lấy trạng thái toàn bộ 3 cụm ESP32 | `GET /api/mqtt/state` | *(Không có)* |
| Lấy lịch sử sự kiện gần nhất | `GET /api/mqtt/logs` | *(Không có)* |
| Điều khiển Đèn / Còi Cụm ESP 1 | `POST /api/mqtt/cluster1/control` | `{"mode": "MANUAL", "light": true, "buzzer": false}` |
| Chuyển Cụm ESP 1 về Tự động | `POST /api/mqtt/cluster1/control` | `{"mode": "AUTO"}` |
| Điều khiển Đèn / Quạt Cụm ESP 2 | `POST /api/mqtt/cluster2/control` | `{"mode": "MANUAL", "light": true, "fan": true}` |
| Chuyển Cụm ESP 2 về Tự động | `POST /api/mqtt/cluster2/control` | `{"mode": "AUTO"}` |
| Yêu cầu ESP32-CAM chụp ảnh ngay | `POST /api/mqtt/cam/capture` | *(Không có)* |
| Mở cửa Servo SG90 ($90^\circ$) từ Web | `POST /api/mqtt/cam/door` | `{"identity": "KNOWN", "authorized": true, "person_name": "Admin"}` |
| Khóa cửa Servo SG90 ($0^\circ$) từ Web | `POST /api/mqtt/cam/door` | `{"identity": "UNKNOWN", "authorized": false}` |
