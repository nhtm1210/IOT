# Hệ Thống Nhà Thông Minh IoT Tích Hợp AI (Firmware & MQTT Base)

Repository này chứa toàn bộ **Firmware cho 3 cụm phần cứng ESP32** cùng **Bộ giao tiếp MQTT & AI mẫu (`mqtt-sample/`)** đã hoàn thiện để **Thành viên 2 (Backend)** phát triển trực tiếp trên đó.

---

## 1. Cấu trúc Repository

```text
├── esp32-cluster1-test/              # Firmware Cụm ESP 1 (Cảm biến chuyển động PIR + Đèn + Còi)
├── esp32-cluster2-test/              # Firmware Cụm ESP 2 (DHT22 Nhiệt độ/Độ ẩm + Ánh sáng + Đèn + Quạt)
├── esp32-cam/                        # Firmware ESP32-CAM (Nhận diện mặt chủ nhà + Mở cửa Servo SG90)
├── mqtt-sample/                      # Bộ MQTT Broker + Handler + Server FastAPI mẫu cho Thành viên 2
│   ├── broker.py                     # MQTT 3.1.1 Broker tích hợp bằng Python (không cần cài Docker/Mosquitto)
│   ├── mqtt_handler.py               # Class SmartHomeMqttService quản lý toàn bộ MQTT Topics & JSON
│   ├── server_mqtt_sample.py         # Server FastAPI mẫu + Nhận diện mặt chủ nhà + Điều khiển 3 cụm
│   ├── simulator_esp32.py            # Giả lập cả 3 cụm ESP32 để test Backend khi chưa cắm mạch thật
│   ├── requirements.txt              # Thư viện Python cần thiết
│   └── README.md                     # Hướng dẫn chạy cho Thành viên 2
├── MQTT_SPEC.md                      # Đặc tả chi tiết 16 MQTT Topics & JSON Schema
└── TONG_QUAN_DU_AN_SMART_HOME_IOT.md # Tài liệu tổng quan đề tài & phân công 3 thành viên
```

---

## 2. Kịch bản hoạt động của 3 cụm ESP32

### Cụm ESP 1 (`esp32-cluster1-test`)
- **Sơ đồ chân (`include/pins.h`):** `PIN_PIR = 27` (HC-SR501), `PIN_LED = 26` (Đèn), `PIN_BUZZER = 25` (Còi).
- **Kịch bản:** Khi có chuyển động, cảm biến PIR ghi nhận $\rightarrow$ **còi kêu và đèn sáng ngay lập tức**, duy trì 5 giây sau lần chuyển động cuối cùng rồi tự tắt. Gửi sự kiện qua MQTT (`smarthome/security/motion` và `smarthome/sensor/cluster1`) và nhận lệnh điều khiển từ xa qua `smarthome/device/cluster1/command`.

### Cụm ESP 2 (`esp32-cluster2-test`)
- **Sơ đồ chân (`include/pins.h`):** `PIN_DHT = 4` (DHT22), `PIN_LDR_ANALOG = 34` (LDR ADC), `PIN_I2C_SDA = 22` / `PIN_I2C_SCL = 21` (BH1750), `PIN_LIGHT_OUTPUT = 2` (Đèn), `PIN_FAN_RELAY = 5` (Quạt).
- **Kịch bản:**
  - **Quạt:** Kiểm tra nếu **độ ẩm thấp** ($\le 40\%$) **và nhiệt độ cao** ($\ge 30^\circ\text{C}$) sẽ **bật quạt**, không thỏa điều kiện sẽ **tắt quạt**.
  - **Đèn:** Cảm biến ánh sáng ghi nhận nếu **trời tối** (`ADC < 2000`) sẽ **bật đèn** và **trời sáng** (`ADC >= 2000`) sẽ **tắt đèn**.
  - Định kỳ 2 giây gửi dữ liệu lên `smarthome/sensor/cluster2` và nhận lệnh điều khiển qua `smarthome/device/cluster2/command`.

### Cụm Camera AI (`esp32-cam`)
- **Sơ đồ chân (`include/pins.h`):** Camera OV2640 (AI Thinker) + Động cơ **Servo SG90** tại `SERVO_PIN = 13` ($0^\circ$ = khóa cửa, $90^\circ$ = mở cửa trong 5 giây).
- **Kịch bản:**
  - Khi nhận sự kiện chuyển động từ Cụm 1 hoặc bấm chụp trên trang Web của Camera (`http://<ip-cam>/`), ESP32-CAM chụp ảnh JPEG gửi về Backend (`POST /api/security/recognize`) để đối chiếu với khuôn mặt chủ nhà đã lưu sẵn.
  - **Nếu khớp mặt chủ nhà (`KNOWN`, `authorized: true`, `action: "OPEN"`):** Động cơ Servo SG90 **quay góc $90^\circ$ để mở cửa**, giữ 5 giây rồi tự động quay về $0^\circ$ đóng cửa.
  - **Nếu không khớp (`UNKNOWN` hoặc `NO_FACE`):** Động cơ Servo SG90 **không quay** (giữ nguyên ở góc $0^\circ$).

---

## 3. Hướng dẫn nạp Firmware (Thành viên 1)

Trong mỗi thư mục (`esp32-cluster1-test`, `esp32-cluster2-test`, `esp32-cam`), sao chép `include/secrets.example.h` thành `include/secrets.h`, điền thông tin Wi-Fi cùng địa chỉ IP LAN của máy tính chạy Backend, sau đó nạp code bằng PlatformIO:

```powershell
pio run -t upload
pio device monitor -b 115200
```

---

## 4. Hướng dẫn chạy MQTT Mẫu & Phát triển Backend (Thành viên 2)

```powershell
cd mqtt-sample
pip install -r requirements.txt
python server_mqtt_sample.py
```
- Lệnh trên tự động bật cả **MQTT Broker ở cổng `1883`** và **FastAPI Server ở cổng `8000`**.
- Mở Swagger UI tại: `http://localhost:8000/docs`
- Để giả lập dữ liệu từ cả 3 cụm ESP32 khi chưa cắm mạch thật, mở thêm 1 terminal chạy:
  ```powershell
  cd mqtt-sample
  python simulator_esp32.py
  ```
- Xem chi tiết toàn bộ MQTT Topics & JSON Schema tại [MQTT_SPEC.md](MQTT_SPEC.md).
