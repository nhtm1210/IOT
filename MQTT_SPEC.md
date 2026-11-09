# ĐẶC TẢ GIAO THỨC MQTT & HTTP (FIRMWARE ↔ BACKEND CONTRACT)

> **Phiên bản:** `1.1.0` (`schema_version = 1`)  
> **Người bàn giao:** Thành viên 1 (Hardware & Embedded Developer)  
> **Người nhận bàn giao:** Thành viên 2 (Backend Developer - FastAPI + Mosquitto + SQLite)

Tài liệu này định nghĩa toàn bộ giao thức truyền thông giữa **3 cụm phần cứng ESP32** (`esp32_cluster1`, `esp32_cluster2`, `esp32_cam_01`) và **Backend** để Thành viên 2 xây dựng MQTT Subscriber/Publisher, Database và REST API.

---

## 1. Tổng quan 3 cụm thiết bị và kịch bản hoạt động

1. **Cụm ESP 1 (`esp32_cluster1` - `firmware/esp32-cluster1-test`):**
   - **Phần cứng:** Cảm biến chuyển động PIR (`GPIO 27`), Đèn LED (`GPIO 26`), Còi Buzzer (`GPIO 25`).
   - **Kịch bản tự động (`AUTO`):** Khi cảm biến PIR phát hiện có chuyển động, cụm ESP 1 lập tức **bật đèn sáng và bật còi kêu** trong 5 giây (gia hạn nếu vẫn còn chuyển động), đồng thời gửi bản tin sự kiện chuyển động qua MQTT. Khi hết chuyển động sau 5 giây, đèn và còi tự động tắt.
   - **Điều khiển từ xa (`MANUAL`):** Hỗ trợ nhận lệnh MQTT từ Backend để chuyển chế độ `AUTO`/`MANUAL` hoặc bật/tắt đèn, còi từ xa và trả về `ACK` + `status`.

2. **Cụm ESP 2 (`esp32_cluster2` - `firmware/esp32-cluster2-test`):**
   - **Phần cứng:** Cảm biến nhiệt độ & độ ẩm DHT22 (`GPIO 4`), Cảm biến ánh sáng LDR ADC (`GPIO 34`) + BH1750 I2C (`SDA=22, SCL=21`), Đèn (`GPIO 2`), Quạt qua Relay/MOSFET (`GPIO 5`).
   - **Kịch bản tự động (`AUTO`):**
     - **Điều khiển quạt:** Kiểm tra nếu **độ ẩm thấp** (`humidity_pct <= 40.0%`) **VÀ nhiệt độ cao** (`temperature_c >= 30.0°C`) thì **bật quạt**, ngược lại **sẽ tắt quạt**.
     - **Điều khiển đèn:** Cảm biến ánh sáng ghi nhận nếu **trời tối** (`light_adc < 2000`, `is_dark = true`) sẽ **bật đèn**, và **trời sáng** (`is_dark = false`) sẽ **tắt đèn**.
   - **Điều khiển từ xa (`MANUAL`):** Hỗ trợ nhận lệnh MQTT từ Backend để chuyển chế độ `AUTO`/`MANUAL` hoặc bật/tắt đèn, quạt từ xa và trả về `ACK` + `status`.

3. **Cụm Camera AI (`esp32_cam_01` - `firmware/esp32-cam`):**
   - **Phần cứng:** AI Thinker ESP32-CAM (OV2640) + Động cơ **Servo SG90** điều khiển cửa (`GPIO 13`).
   - **Kịch bản nhận diện chủ nhà & mở cửa:**
     - Khi nhận sự kiện có chuyển động từ Cụm 1 (`smarthome/security/motion`), hoặc người dùng bấm chụp trên trang Web của Camera (`http://<ip-cam>/`), hoặc nhận lệnh `CAPTURE` từ Backend, ESP32-CAM chụp ảnh JPEG và gửi qua HTTP `POST /api/security/recognize` về Backend (nơi lưu sẵn mẫu khuôn mặt chủ nhà).
     - **Nếu khớp với mặt chủ nhà đã lưu sẵn** (`identity = "KNOWN"`, `authorized = true`, `action = "OPEN"`): Động cơ **Servo SG90 quay góc `90°` để mở cửa**, giữ mở 5 giây rồi tự động quay về `0°` để đóng cửa.
     - **Nếu không khớp** (`identity = "UNKNOWN"` hoặc `"NO_FACE"`, `authorized = false`, `action = "KEEP_LOCKED"`): Động cơ **Servo SG90 không quay** (giữ nguyên góc `0°` - khóa cửa).

---

## 2. Cấu hình MQTT Broker chung

- **Broker:** Mosquitto MQTT chạy trên máy Backend (cổng TCP `1883`, lắng nghe trên địa chỉ IP LAN của máy chạy Backend, ví dụ `192.168.1.10:1883`).
- **Định dạng bản tin:** JSON UTF-8, luôn có trường `"schema_version": 1`.
- **Device IDs cố định:**
  - Cụm 1: `esp32_cluster1`
  - Cụm 2: `esp32_cluster2`
  - ESP32-CAM: `esp32_cam_01`
- **QoS & Retain:**
  - Các bản tin trạng thái thiết bị (`.../status`) được publish với `retain = true` (bao gồm cả Last Will `"online": false` khi mất nguồn/mất mạng).
  - Các bản tin sự kiện cảm biến (`.../sensor/...`, `.../motion`), lệnh điều khiển (`.../command`) và xác nhận (`.../ack`) dùng `retain = false`.

---

## 3. Bảng tổng hợp các MQTT Topics

| STT | Topic | Chiều truyền | Retain | Mô tả |
|---|---|---|---|---|
| 1 | `smarthome/security/motion` | Cụm 1 → Backend & CAM | `false` | Sự kiện phát hiện chuyển động (`MOTION_DETECTED`) |
| 2 | `smarthome/sensor/cluster1` | Cụm 1 → Backend | `false` | Trạng thái PIR (`MOTION_DETECTED` / `MOTION_CLEARED`) & đèn/còi Cụm 1 |
| 3 | `smarthome/device/cluster1/command` | Backend → Cụm 1 | `false` | Lệnh điều khiển đèn/còi & chế độ `AUTO`/`MANUAL` Cụm 1 |
| 4 | `smarthome/device/cluster1/ack` | Cụm 1 → Backend | `false` | Xác nhận thực thi lệnh điều khiển của Cụm 1 |
| 5 | `smarthome/device/cluster1/status` | Cụm 1 → Backend | `true` | Trạng thái hiện tại của đèn, còi, PIR, mode Cụm 1 |
| 6 | `smarthome/system/cluster1/status` | Cụm 1 → Backend | `true` | Trạng thái Online/Offline (Last Will) của Cụm 1 |
| 7 | `smarthome/sensor/cluster2` | Cụm 2 → Backend | `false` | Dữ liệu nhiệt độ, độ ẩm, ánh sáng (LDR + BH1750) mỗi 2 giây |
| 8 | `smarthome/device/cluster2/command` | Backend → Cụm 2 | `false` | Lệnh điều khiển đèn/quạt & chế độ `AUTO`/`MANUAL` Cụm 2 |
| 9 | `smarthome/device/cluster2/ack` | Cụm 2 → Backend | `false` | Xác nhận thực thi lệnh điều khiển của Cụm 2 |
| 10 | `smarthome/device/cluster2/status` | Cụm 2 → Backend | `true` | Trạng thái hiện tại của đèn, quạt, mode Cụm 2 |
| 11 | `smarthome/system/cluster2/status` | Cụm 2 → Backend | `true` | Trạng thái Online/Offline (Last Will) của Cụm 2 |
| 12 | `smarthome/security/recognition` | CAM / Backend → Backend | `false` | Sự kiện kết quả nhận diện khuôn mặt & trạng thái mở cửa |
| 13 | `smarthome/security/access/esp32_cam_01/command` | Backend → CAM | `false` | Lệnh mở cửa (`OPEN`), giữ khóa (`KEEP_LOCKED`) hoặc chụp ảnh (`CAPTURE`) |
| 14 | `smarthome/security/access/esp32_cam_01/ack` | CAM → Backend | `false` | Xác nhận đã quay Servo SG90 mở cửa hoặc giữ khóa cửa |
| 15 | `smarthome/device/esp32_cam_01/status` | CAM → Backend | `true` | Trạng thái camera, cửa (`OPEN`/`LOCKED`), góc servo SG90 (`0`/`90`) |
| 16 | `smarthome/system/esp32_cam_01/status` | CAM → Backend | `true` | Trạng thái Online/Offline (Last Will) của ESP32-CAM |

> **Mẹo cho Backend Developer:** Khi viết Paho-MQTT Subscriber, có thể subscribe wildcard `smarthome/#` rồi phân nhánh xử lý theo tên `topic`.

---

## 4. Chi tiết Payload JSON từng cụm

### 4.1. Cụm ESP 1 (`esp32_cluster1`) — Chuyển động, Còi & Đèn

#### A. Sự kiện chuyển động & cảm biến
- **Topic:** `smarthome/security/motion` (chỉ gửi khi `pir = true`) và `smarthome/sensor/cluster1` (gửi cả khi `MOTION_DETECTED` và `MOTION_CLEARED`).
```json
{
  "schema_version": 1,
  "event_id": "motion_12ab34cd_1",
  "device_id": "esp32_cluster1",
  "event_type": "MOTION_DETECTED",
  "pir": true,
  "outputs": {
    "light": true,
    "buzzer": true
  },
  "timestamp_ms": 23841
}
```
Khi hết chuyển động sau 5 giây (`MOTION_CLEARED`), Cụm 1 gửi lên `smarthome/sensor/cluster1`:
```json
{
  "schema_version": 1,
  "event_id": "motion_12ab34cd_2",
  "device_id": "esp32_cluster1",
  "event_type": "MOTION_CLEARED",
  "pir": false,
  "outputs": {
    "light": false,
    "buzzer": false
  },
  "timestamp_ms": 28845
}
```

#### B. Trạng thái thiết bị Cụm 1
- **Topic:** `smarthome/device/cluster1/status` (Retained)
```json
{
  "schema_version": 1,
  "device_id": "esp32_cluster1",
  "online": true,
  "mode": "AUTO",
  "pir": true,
  "outputs": {
    "light": true,
    "buzzer": true
  },
  "firmware_version": "1.1.0"
}
```

#### C. Lệnh điều khiển Cụm 1 từ Backend (tùy chọn khi điều khiển trên Web)
- **Topic:** `smarthome/device/cluster1/command`
- **Cách 1 (điều khiển từng thiết bị `light_1` hoặc `buzzer_1`):**
```json
{
  "schema_version": 1,
  "command_id": "cmd_c1_001",
  "device_id": "buzzer_1",
  "state": "OFF",
  "mode": "MANUAL"
}
```
- **Cách 2 (điều khiển gộp hoặc đổi lại về chế độ `AUTO`):**
```json
{
  "schema_version": 1,
  "command_id": "cmd_c1_002",
  "device_id": "esp32_cluster1",
  "mode": "AUTO",
  "outputs": {
    "light": false,
    "buzzer": false
  }
}
```

#### D. Phản hồi ACK từ Cụm 1
- **Topic:** `smarthome/device/cluster1/ack`
```json
{
  "schema_version": 1,
  "command_id": "cmd_c1_001",
  "device_id": "esp32_cluster1",
  "mode": "MANUAL",
  "success": true,
  "error": null,
  "outputs": {
    "light": true,
    "buzzer": false
  },
  "timestamp_ms": 30120
}
```

---

### 4.2. Cụm ESP 2 (`esp32_cluster2`) — Nhiệt độ/Độ ẩm (Quạt) & Ánh sáng (Đèn)

#### A. Bản tin dữ liệu cảm biến định kỳ (2 giây/lần)
- **Topic:** `smarthome/sensor/cluster2`
```json
{
  "schema_version": 1,
  "message_id": "cluster2_56ef78ab_1",
  "device_id": "esp32_cluster2",
  "mode": "AUTO",
  "timestamp_ms": 12000,
  "temperature_c": 31.5,
  "humidity_pct": 38.0,
  "light_adc": 1400,
  "light_lux": 12.4,
  "is_dark": true,
  "outputs": {
    "light": true,
    "fan": true
  }
}
```
- **Lưu ý cho Backend:**
  - Nếu cảm biến DHT22 hoặc BH1750 chưa cắm hoặc đọc lỗi, `temperature_c`, `humidity_pct`, `light_lux` sẽ có giá trị `null`. Backend cần cho phép `Optional[float] = None`.
  - Quy tắc tự động trên Cụm 2 khi `mode == "AUTO"`:
    - `temperature_c >= 30.0` **VÀ** `humidity_pct <= 40.0` → `outputs.fan = true`, ngược lại `outputs.fan = false`.
    - `is_dark == true` (`light_adc < 2000`) → `outputs.light = true`, ngược lại `outputs.light = false`.

#### B. Trạng thái thiết bị Cụm 2
- **Topic:** `smarthome/device/cluster2/status` (Retained)
```json
{
  "schema_version": 1,
  "device_id": "esp32_cluster2",
  "online": true,
  "mode": "AUTO",
  "outputs": {
    "light": true,
    "fan": true
  },
  "firmware_version": "1.1.0"
}
```

#### C. Lệnh điều khiển Cụm 2 từ Backend
- **Topic:** `smarthome/device/cluster2/command`
- **Cách 1 (bật/tắt từng thiết bị `light_2` / `light_1` hoặc `fan_1`):**
```json
{
  "schema_version": 1,
  "command_id": "cmd_c2_001",
  "device_id": "fan_1",
  "state": "ON",
  "mode": "MANUAL"
}
```
- **Cách 2 (điều khiển gộp hoặc chuyển về chế độ `AUTO`):**
```json
{
  "schema_version": 1,
  "command_id": "cmd_c2_002",
  "device_id": "esp32_cluster2",
  "mode": "AUTO"
}
```

#### D. Phản hồi ACK từ Cụm 2
- **Topic:** `smarthome/device/cluster2/ack`
```json
{
  "schema_version": 1,
  "command_id": "cmd_c2_001",
  "device_id": "esp32_cluster2",
  "mode": "MANUAL",
  "success": true,
  "error": null,
  "outputs": {
    "light": true,
    "fan": true
  },
  "timestamp_ms": 16420
}
```

---

### 4.3. Cụm Camera AI (`esp32_cam_01`) — Nhận diện mặt chủ nhà & Mở cửa Servo SG90

#### A. Luồng gửi ảnh từ ESP32-CAM lên Backend qua HTTP POST
Khi Cụm 1 phát hiện chuyển động (hoặc khi người dùng nhấn nút trên trang web của ESP32-CAM), `esp32_cam_01` chụp ảnh JPEG và gửi HTTP request đến Backend:

```http
POST /api/security/recognize HTTP/1.1
Host: <BACKEND_IP>:8000
Content-Type: image/jpeg
X-Device-Id: esp32_cam_01
X-Event-Id: motion_12ab34cd_1
```
*(Nếu người dùng nhấn nút **"Lưu mặt chủ nhà (Enroll)"** trên trang Web của ESP32-CAM, request sẽ có thêm header `X-Mode: ENROLL_OWNER` và `X-Person-Name: owner` để Backend lưu ảnh mẫu chủ nhà).*

#### B. Kết quả nhận diện và Lệnh đóng/mở cửa từ Backend xuống ESP32-CAM
Sau khi Backend đối chiếu ảnh JPEG với khuôn mặt chủ nhà đã được lưu sẵn, Backend có thể trả kết quả theo **1 trong 2 cách (hoặc cả 2, ESP32-CAM hỗ trợ cả hai và tự chống trùng lặp qua `command_id`)**:

1. **Publish MQTT tới topic:** `smarthome/security/access/esp32_cam_01/command` (QoS 1, `retain = false`)
2. **Hoặc trả trực tiếp JSON trên trong HTTP 200 Response** của `POST /api/security/recognize`.

- **Trường hợp 1: Khớp khuôn mặt chủ nhà đã lưu sẵn → Quay Servo SG90 mở cửa (90° trong 5 giây):**
```json
{
  "schema_version": 1,
  "command_id": "access_00042",
  "event_id": "motion_12ab34cd_1",
  "device_id": "esp32_cam_01",
  "identity": "KNOWN",
  "person_name": "Chu_Nha",
  "confidence": 0.92,
  "authorized": true,
  "action": "OPEN"
}
```

- **Trường hợp 2: Không khớp mặt chủ nhà (`UNKNOWN` hoặc `NO_FACE`) → Servo SG90 không quay (giữ khóa ở 0°):**
```json
{
  "schema_version": 1,
  "command_id": "access_00043",
  "event_id": "motion_12ab34cd_2",
  "device_id": "esp32_cam_01",
  "identity": "UNKNOWN",
  "person_name": "unknown",
  "confidence": 0.41,
  "authorized": false,
  "action": "KEEP_LOCKED"
}
```

- **Trường hợp 3: Backend chủ động yêu cầu ESP32-CAM chụp ảnh ngay:**
```json
{
  "schema_version": 1,
  "command_id": "access_00044",
  "event_id": "manual_check_01",
  "device_id": "esp32_cam_01",
  "action": "CAPTURE"
}
```

#### C. Bản tin ACK và Sự kiện nhận diện từ ESP32-CAM gửi về Backend
Ngay khi thực hiện kiểm tra và điều khiển Servo SG90, ESP32-CAM publish đồng thời:

1. **Topic ACK:** `smarthome/security/access/esp32_cam_01/ack`
```json
{
  "schema_version": 1,
  "command_id": "access_00042",
  "event_id": "motion_12ab34cd_1",
  "device_id": "esp32_cam_01",
  "identity": "KNOWN",
  "success": true,
  "error": null,
  "door_state": "OPEN",
  "servo_angle_deg": 90,
  "timestamp_ms": 24100
}
```

2. **Topic Sự kiện nhận diện:** `smarthome/security/recognition`
```json
{
  "schema_version": 1,
  "event_id": "motion_12ab34cd_1",
  "device_id": "esp32_cam_01",
  "identity": "KNOWN",
  "person_name": "Chu_Nha",
  "confidence": 0.92,
  "authorized": true,
  "door_action": "OPEN",
  "door_state": "OPEN",
  "timestamp_ms": 24100
}
```

3. **Topic Trạng thái Camera & Cửa:** `smarthome/device/esp32_cam_01/status` (Retained)
```json
{
  "schema_version": 1,
  "device_id": "esp32_cam_01",
  "online": true,
  "camera_ready": true,
  "door_state": "OPEN",
  "servo_angle_deg": 90,
  "last_identity": "KNOWN",
  "last_person_name": "Chu_Nha",
  "firmware_version": "1.1.0"
}
```
*(Sau 5 giây mở cửa, ESP32-CAM tự động quay Servo SG90 về `0°` và publish lại `door_state: "LOCKED"`, `servo_angle_deg: 0` lên `smarthome/device/esp32_cam_01/status`).*

---

## 5. Hướng dẫn nhanh cho Thành viên 2 (Backend Developer)

### 5.1. Các Topic Backend cần Subscribe
Trong Paho-MQTT, khi kết nối tới Broker thành công (`on_connect`), subscribe:
- `smarthome/security/motion`
- `smarthome/security/recognition`
- `smarthome/security/access/esp32_cam_01/ack`
- `smarthome/sensor/+` (`cluster1`, `cluster2`)
- `smarthome/device/+/status`
- `smarthome/device/+/ack`
- `smarthome/system/+/status`

### 5.2. Endpoint FastAPI cần viết cho ESP32-CAM (`POST /api/security/recognize`)
```python
from fastapi import APIRouter, Header, Request
import uuid

router = APIRouter()

@router.post("/api/security/recognize")
async def recognize_face(
    request: Request,
    x_device_id: str = Header(default="esp32_cam_01"),
    x_event_id: str = Header(default=""),
    x_mode: str = Header(default="RECOGNIZE"),
    x_person_name: str = Header(default="owner"),
):
    image_bytes = await request.body()
    event_id = x_event_id or f"evt_{uuid.uuid4().hex[:8]}"

    # Nếu header X-Mode == "ENROLL_OWNER": lưu ảnh mẫu chủ nhà
    if x_mode == "ENROLL_OWNER":
        save_owner_face_template(image_bytes, person_name=x_person_name)
        return {"status": "enrolled", "person_name": x_person_name, "event_id": event_id}

    # So khớp khuôn mặt với mẫu mặt chủ nhà đã lưu sẵn
    # identity nhận 1 trong 3 giá trị: "KNOWN", "UNKNOWN", "NO_FACE"
    identity, person_name, confidence = match_owner_face(image_bytes)
    authorized = (identity == "KNOWN")
    action = "OPEN" if authorized else "KEEP_LOCKED"
    command_id = f"access_{uuid.uuid4().hex[:8]}"

    payload = {
        "schema_version": 1,
        "command_id": command_id,
        "event_id": event_id,
        "device_id": x_device_id,
        "identity": identity,
        "person_name": person_name,
        "confidence": round(float(confidence), 3),
        "authorized": authorized,
        "action": action,
    }

    # Gửi lệnh qua MQTT xuống ESP32-CAM VÀ trả về trong HTTP response
    mqtt_publish("smarthome/security/access/esp32_cam_01/command", payload, qos=1, retain=False)
    return payload
```
