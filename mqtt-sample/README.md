# Bộ MQTT Mẫu & Server Tích Hợp Sẵn (Dành cho Thành viên 1 & Thành viên 2)

Thư mục `mqtt-sample/` chứa toàn bộ **code giao tiếp MQTT mẫu đã hoàn chỉnh** với 3 cụm ESP32 (`esp32_cluster1`, `esp32_cluster2`, `esp32_cam_01`), giúp:
1. **Thành viên 1 (Phần cứng/Firmware):** Chạy thử nghiệm ngay toàn bộ luồng MQTT + Nhận diện khuôn mặt chủ nhà mở cửa Servo SG90 với mạch thật (hoặc bằng script giả lập).
2. **Thành viên 2 (Backend Developer):** Chỉ cần import trực tiếp class `SmartHomeMqttService` trong [`mqtt_handler.py`](mqtt_handler.py) và mở rộng [`server_mqtt_sample.py`](server_mqtt_sample.py) để gắn thêm Database (SQLite/SQLAlchemy), JWT Auth và Telegram Bot.

---

## 1. Các file trong thư mục

- [`broker.py`](broker.py): MQTT 3.1.1 Broker viết bằng Python `asyncio` thuần, lắng nghe ở cổng `1883` trên toàn mạng LAN (không cần cài Mosquitto rời hay bật Docker Desktop).
- [`mqtt_handler.py`](mqtt_handler.py): Module lõi `SmartHomeMqttService` (Paho-MQTT), tự động subscribe toàn bộ topics của 3 cụm ESP32, giải mã JSON, lưu trạng thái thời gian thực và cung cấp sẵn các hàm gửi lệnh:
  - `control_cluster1(mode, light, buzzer)`
  - `control_cluster2(mode, light, fan)`
  - `send_door_access_decision(identity, authorized, person_name, confidence, event_id)`
  - `request_camera_capture()`
- [`server_mqtt_sample.py`](server_mqtt_sample.py): Server FastAPI mẫu chạy kèm `SmartHomeMqttService` và `EmbeddedMqttBroker`:
  - Nhận ảnh JPEG từ ESP32-CAM tại `POST /api/security/recognize`.
  - Lưu ảnh mẫu mặt chủ nhà vào `owner_faces/owner.jpg` khi nhấn nút **"Lưu mặt chủ nhà (Enroll)"** trên trang web của ESP32-CAM.
  - Đối chiếu khuôn mặt với mẫu mặt chủ nhà đã lưu sẵn $\rightarrow$ tự động gửi lệnh MQTT `OPEN` (quay Servo SG90 góc $90^\circ$ mở cửa) nếu khớp (`KNOWN`), hoặc `KEEP_LOCKED` (giữ Servo SG90 góc $0^\circ$) nếu không khớp (`UNKNOWN` / `NO_FACE`).
  - Cung cấp giao diện Swagger UI tại `http://localhost:8000/docs`.
- [`simulator_esp32.py`](simulator_esp32.py): Script giả lập đồng thời cả 3 cụm ESP32 gửi dữ liệu cảm biến và phản hồi lệnh điều khiển qua MQTT (dùng để test khi chưa cắm mạch thật).

---

## 2. Hướng dẫn chạy nhanh (Quick Start)

### Bước 1: Cài đặt thư viện và khởi chạy Server (tự động bật Broker cổng 1883 + Web cổng 8000)
```powershell
cd mqtt-sample
pip install -r requirements.txt
python server_mqtt_sample.py
```
Sau khi chạy, mở trình duyệt truy cập: **`http://localhost:8000/docs`**

### Bước 2: Kết nối với mạch ESP32 thật (hoặc chạy bộ giả lập)
- **Cách A — Dùng mạch ESP32 thật:** Điền IP LAN của máy tính (hiển thị trên cửa sổ chạy `server_mqtt_sample.py`) vào `include/secrets.h` của 3 project firmware rồi nạp code.
- **Cách B — Chạy bộ giả lập 3 cụm ESP32 ngay trên máy tính (mở thêm 1 cửa sổ terminal):**
  ```powershell
  cd mqtt-sample
  python simulator_esp32.py
  ```

---

## 3. Hướng dẫn cho Thành viên 2 (Backend) gắn Database

Trong [`server_mqtt_sample.py`](server_mqtt_sample.py), các callback nhận dữ liệu từ 3 cụm ESP32 đã được tách sẵn:

```python
mqtt_service.on_motion_event = lambda payload: ...       # Lưu sự kiện chuyển động Cụm 1 + gửi cảnh báo Telegram
mqtt_service.on_cluster1_sensor = lambda payload: ...    # Lưu lịch sử PIR + đèn/còi Cụm 1 vào bảng SensorHistory
mqtt_service.on_cluster2_sensor = lambda payload: ...    # Lưu nhiệt độ, độ ẩm, ánh sáng Cụm 2 vào bảng SensorHistory
mqtt_service.on_device_ack = lambda dev_id, payload: ... # Cập nhật trạng thái lệnh điều khiển vào bảng DeviceHistory
mqtt_service.on_recognition_event = lambda payload: ...  # Lưu lịch sử nhận diện mặt chủ nhà vào bảng Recognitions
```
