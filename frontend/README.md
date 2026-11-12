# Smart Home IoT Frontend

Ứng dụng React + Vite + TypeScript cho ba cụm ESP32 theo API hiện có trong `../backend/`. Gồm đăng nhập, dashboard thời gian thực, điều khiển thiết bị, tự động hóa, an ninh AI, giọng nói, lịch sử, cài đặt và quản lý người dùng.

## Chạy thử

Mở ba cửa sổ PowerShell trong `D:\iotsmarthome`:

Nếu chưa có môi trường Python trong `backend/.venv`, tạo và cài thư viện trước:

```powershell
python -m venv backend\.venv
python -m pip --python backend\.venv install pip -r backend\requirements.txt
```

```powershell
# Cửa sổ 1: Backend + MQTT broker
$env:PYTHONIOENCODING='utf-8'
.\backend\.venv\Scripts\python.exe .\backend\run.py
```

```powershell
# Cửa sổ 2: Giả lập ba cụm ESP32 khi chưa có mạch
$env:PYTHONIOENCODING='utf-8'
.\backend\.venv\Scripts\python.exe .\mqtt-sample\simulator_esp32.py
```

```powershell
# Cửa sổ 3: Frontend ở http://localhost:5173
cd .\frontend
npm install
npm run dev
```

Backend cũng phục vụ bản build frontend tại `http://localhost:8000` nếu chạy `npm run build` trước khi khởi động backend. API tương tác: `http://localhost:8000/docs`.

Backend hiện seed tài khoản demo `admin/admin123`, `user/user123`, `guest/guest123` vào database mới. `GUEST` chỉ xem; `USER` điều khiển; `ADMIN` quản lý tài khoản. Đổi mật khẩu trước khi dùng ngoài môi trường demo.

## Cấu hình

Sao chép `.env.example` thành `.env` nếu backend ở máy khác. Đặt `VITE_API_BASE_URL` và `VITE_WS_URL` theo IP của máy chạy backend. Khi không có `.env`, frontend tự dùng hostname hiện tại với cổng 8000.

Frontend gọi REST API để lấy trạng thái đầu tiên, nhận cập nhật qua `/ws/dashboard` và tự chuyển sang polling 10 giây nếu WebSocket mất kết nối. Lệnh điều khiển được giữ ở trạng thái chờ cho đến khi nhận ACK khớp `command_id` hoặc status từ thiết bị. Nếu quá 12 giây chưa xác nhận, giao diện báo trạng thái chưa xác nhận.

Giọng nói dùng Web Speech API tiếng Việt trên trình duyệt hỗ trợ. “Bật đèn” mặc định là đèn phòng Cụm 2; có thể nói “đèn cảnh báo” cho Cụm 1. Nút điều khiển vẫn dùng được khi trình duyệt không có nhận dạng giọng nói.

Tài liệu giao tiếp: `../API_SPEC.md`, `../MQTT_SPEC.md`, `../WEB_DASHBOARD_SPEC.md`. Giao diện theo API ba cụm ESP32 của backend hiện tại.
