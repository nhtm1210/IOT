# Hệ Thống Nhà Thông Minh IoT Tích Hợp AI (Full-Stack: Firmware + Backend + Frontend)

Dự án hoàn chỉnh đã gộp chung cả **3 thành phần** của nhóm:
1. **Thành viên 1 (`firmware/` & `mqtt-sample/`):** Firmware PlatformIO cho 3 cụm phần cứng ESP32 (`esp32-cluster1-test`, `esp32-cluster2-test`, `esp32-cam`) + Bộ giả lập MQTT (`simulator_esp32.py`).
2. **Thành viên 2 (`backend/`):** Hệ thống Backend FastAPI + SQLite + Embedded MQTT Broker (cổng `1883`) + Nhận diện khuôn mặt AI OpenCV + Tự động hóa + WebSocket thời gian thực + Telegram Bot.
3. **Thành viên 3 (`frontend/`):** Giao diện Web Dashboard React + Vite + TypeScript + Tailwind CSS + Recharts + Điều khiển giọng nói tiếng Việt (Web Speech API).

---

## 1. Cấu trúc Dự án Hợp nhất

```text
IOT/
├── firmware/                         # Phần cứng & Firmware 3 cụm ESP32 (Thành viên 1)
│   ├── esp32-cluster1-test/          # Cụm ESP 1: Cảm biến chuyển động PIR + Đèn + Còi
│   ├── esp32-cluster2-test/          # Cụm ESP 2: DHT22 Nhiệt độ/Độ ẩm + Ánh sáng LDR/BH1750 + Đèn + Quạt
│   └── esp32-cam/                    # Cụm ESP32-CAM: Nhận diện mặt chủ nhà + Mở cửa Servo SG90
├── backend/                          # Hệ thống Backend chính thức (Thành viên 2)
│   ├── app/                          # Mã nguồn FastAPI (api, core, models, schemas, services, websocket)
│   ├── data/                         # SQLite Database (smarthome.db), ảnh mẫu chủ nhà & lịch sử sự kiện
│   ├── tests/                        # Kiểm thử tự động REST API (test_api.py)
│   ├── requirements.txt              # Thư viện Python cho Backend
│   └── run.py                        # Khởi chạy gộp Backend (cổng 8000) + MQTT Broker (cổng 1883)
├── frontend/                         # Giao diện Web Dashboard React + TypeScript (Thành viên 3)
│   ├── src/                          # Pages (Dashboard, Devices, Automation, Security, History, Settings, Users)
│   ├── package.json                  # Thư viện Node.js (React, Tailwind, Recharts, Lucide, Axios)
│   └── vite.config.ts                # Cấu hình Vite chạy cổng 5173
├── mqtt-sample/                      # Bộ MQTT mẫu & Script giả lập 3 cụm ESP32 (simulator_esp32.py)
├── API_SPEC.md                       # Đặc tả 24 REST API & WebSocket
├── MQTT_SPEC.md                      # Đặc tả 16 MQTT Topics & JSON Schema
├── WEB_DASHBOARD_SPEC.md             # Đặc tả giao diện Web Dashboard
└── TONG_QUAN_DU_AN_SMART_HOME_IOT.md # Tổng quan đề tài & phân công nhiệm vụ
```

---

## 2. Hướng dẫn chạy toàn bộ hệ thống (Backend + Giả lập ESP32 + Frontend)

Mở **3 cửa sổ PowerShell** tại thư mục gốc `C:\Users\Minh\Desktop\Hoc\IOT`:

### Cửa sổ 1: Chạy Backend + MQTT Broker (Cổng 8000 & 1883)
```powershell
cd backend
pip install -r requirements.txt
python run.py
```
*(Nếu lệnh `python` trên Windows mở Microsoft Store, dùng `python3.13 run.py`).*
- Swagger UI: `http://localhost:8000/docs`
- Tài khoản mặc định:
  - Quản trị viên (`ADMIN`): `admin` / `admin123`
  - Người dùng (`USER`): `user` / `user123`
  - Khách (`GUEST`): `guest` / `guest123`

### Cửa sổ 2: Chạy Giả lập 3 cụm ESP32 (Nếu chưa cắm mạch thật)
```powershell
cd mqtt-sample
python simulator_esp32.py
```

### Cửa sổ 3: Chạy Giao diện Web Frontend (Cổng 5173)
```powershell
cd frontend
npm install
npm run dev
```
- Mở trình duyệt truy cập: **`http://localhost:5173`**

*(Mẹo khi đi Demo: Nếu chạy `npm run build` trong thư mục `frontend/`, Backend tại `http://localhost:8000` sẽ tự động phục vụ luôn cả giao diện Web mà không cần bật cửa sổ thứ 3).*

---

## 3. Hướng dẫn nạp Firmware vào 3 mạch ESP32 thật

Trong từng thư mục con của `firmware/` (`firmware/esp32-cluster1-test`, `firmware/esp32-cluster2-test`, `firmware/esp32-cam`):
1. Sao chép `include/secrets.example.h` thành `include/secrets.h`.
2. Điền tên Wi-Fi 2.4GHz, mật khẩu và địa chỉ IP LAN của máy tính đang chạy `backend/run.py`.
3. Biên dịch và nạp code bằng PlatformIO:
   ```powershell
   pio run -t upload
   pio device monitor -b 115200
   ```
