# Smart Home IoT AI — Backend Server (`backend/`)

Đây là mã nguồn **Backend chính thức** của dự án **Hệ thống Nhà thông minh IoT tích hợp AI nhận diện khuôn mặt mở cửa Servo SG90**, được xây dựng bằng **FastAPI + SQLAlchemy 2.0 (SQLite WAL) + Paho-MQTT + Embedded MQTT Broker + OpenCV + WebSocket**.

---

## 1. Cấu trúc thư mục `backend/`

```text
backend/
├── app/
│   ├── api/
│   │   ├── auth.py             # Đăng nhập JWT (/api/auth/login, /api/auth/me) & Quản lý Users (/api/users)
│   │   ├── mqtt_routes.py      # Giám sát & điều khiển trực tiếp 3 cụm ESP32 (/api/mqtt/*)
│   │   ├── sensors.py          # Thông số mới nhất & lịch sử vẽ biểu đồ Recharts (/api/sensors/*)
│   │   ├── devices.py          # Quản lý 5 thiết bị đầu ra & lịch sử lệnh ACK (/api/devices/*)
│   │   ├── security_ai.py      # Nhận diện mặt chủ nhà OpenCV & mở cửa Servo SG90 (/api/security/*, /api/recognitions)
│   │   ├── automation.py       # Quản lý 4 kịch bản tự động hóa (/api/automation/rules)
│   │   └── alerts_settings.py  # Cảnh báo, cài đặt ngưỡng & Telegram Bot (/api/alerts, /api/settings)
│   ├── core/
│   │   ├── config.py           # Nạp biến môi trường từ .env & khởi tạo thư mục lưu trữ
│   │   ├── database.py         # Kết nối SQLite (WAL mode) & SQLAlchemy Session
│   │   └── security.py         # Băm mật khẩu bcrypt, JWT HS256, RBAC (ADMIN/USER/GUEST), Rate Limiter
│   ├── models/
│   │   └── models.py           # 8 bảng cơ sở dữ liệu & hàm seed dữ liệu mặc định
│   ├── schemas/
│   │   └── schemas.py          # Pydantic v2 Schemas kiểm tra dữ liệu đầu vào/đầu ra
│   ├── services/
│   │   ├── broker.py           # MQTT 3.1.1 Broker nhúng sẵn bằng Python asyncio (cổng 1883)
│   │   ├── mqtt_service.py     # Paho-MQTT Subscriber/Publisher đồng bộ DB & WebSocket
│   │   ├── face_recognition.py # Đối chiếu khuôn mặt chủ nhà bằng OpenCV Haar Cascade + Histogram/Template
│   │   ├── automation.py       # Bộ máy đánh giá kịch bản tự động hóa & sinh cảnh báo
│   │   └── telegram_bot.py     # Gửi cảnh báo qua Telegram Bot API
│   ├── websocket/
│   │   └── manager.py          # Quản lý kết nối WebSocket thời gian thực (/ws/dashboard)
│   └── main.py                 # Khởi tạo FastAPI App, CORS, Lifespan & phục vụ gộp Frontend
├── data/
│   ├── smarthome.db            # Cơ sở dữ liệu SQLite (tự động tạo khi chạy)
│   ├── owner_faces/            # Lưu ảnh mẫu mặt chủ nhà (owner.jpg)
│   └── captured_events/        # Lưu ảnh chụp các sự kiện nhận diện từ ESP32-CAM
├── tests/
│   └── test_api.py             # Bộ kiểm thử tự động toàn diện (End-to-End Test)
├── .env.example                # File cấu hình mẫu
├── requirements.txt            # Danh sách thư viện Python
└── run.py                      # Script khởi chạy nhanh Server
```

---

## 2. Hướng dẫn cài đặt và chạy

```powershell
cd backend
pip install -r requirements.txt
python run.py
```

- **Swagger UI (Tài liệu API tương tác):** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/api/health`
- **WebSocket Real-time:** `ws://localhost:8000/ws/dashboard`

### Chạy bộ kiểm thử tự động (Automated Tests):
```powershell
cd backend
python tests/test_api.py
```

---

## 3. Tài liệu cho Thành viên 3 (Frontend)
Xem chi tiết đặc tả toàn bộ API, JSON Schema, WebSocket events và code mẫu Axios/TypeScript tại [`../API_SPEC.md`](../API_SPEC.md) và [`../WEB_DASHBOARD_SPEC.md`](../WEB_DASHBOARD_SPEC.md).
