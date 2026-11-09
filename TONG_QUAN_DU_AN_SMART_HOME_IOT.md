# TỔNG QUAN DỰ ÁN SMART HOME IoT TÍCH HỢP AI

**Tên đề tài:** Hệ thống Nhà thông minh IoT tích hợp AI nhận diện khuôn
mặt phục vụ tự động hóa và bảo mật\
**Quy mô:** 3 thành viên\
**Mục đích tài liệu:** Nắm tổng thể đề tài, phần cứng, kiến trúc, nhiệm
vụ từng người và việc cần làm ngay.

> Trạng thái: Phần cứng đã được lắp theo thông tin hiện có; firmware,
> giao thức MQTT và tích hợp phần mềm đang triển khai. Những cấu hình
> chưa được kiểm tra thực tế được đánh dấu "cần xác nhận".

------------------------------------------------------------------------

## 1. Mục tiêu dự án

Xây dựng hệ thống nhà thông minh có thể giám sát môi trường, điều khiển
thiết bị từ xa, tự động hóa theo điều kiện cài đặt và hỗ trợ giám sát an
ninh bằng camera/AI.

Hệ thống có ba lớp:

1.  **Thiết bị IoT/Embedded:** ESP32 đọc cảm biến, điều khiển thiết bị
    và thu hình ảnh.
2.  **Backend:** Nhận dữ liệu, lưu trữ, xử lý tự động hóa, xác thực
    người dùng, cung cấp API và gửi cảnh báo.
3.  **Frontend:** Giao diện Web để theo dõi, điều khiển, cấu hình và xem
    lịch sử.

## 2. Các tính năng dự kiến

  -----------------------------------------------------------------------
  Tính năng               Mô tả                   Thành phần chính
  ----------------------- ----------------------- -----------------------
  Giám sát môi trường     Nhiệt độ, độ ẩm, ánh    ESP32 #1
                          sáng                    

  Phát hiện chuyển động   Hai vùng cảm biến PIR   ESP32 #1

  Giám sát cửa            Trạng thái đóng/mở khi  ESP32 #1
                          MC-38 được lắp          

  Điều khiển thiết bị     Đèn, quạt, còi          ESP32 #2

  Điều khiển từ xa        Web gửi lệnh qua        Frontend, Backend,
                          Backend và MQTT         ESP32 #2

  Tự động hóa             Bật/tắt thiết bị theo   Backend, ESP32 #2
                          cảm biến và cấu hình    

  An ninh camera/AI       Chụp ảnh, phát hiện và  ESP32-CAM và thành phần
                          thử nghiệm nhận diện    AI
                          khuôn mặt               

  Cảnh báo                Gửi cảnh báo theo sự    Backend
                          kiện qua Telegram       

  Dashboard               Xem cảm biến và trạng   Frontend
                          thái thiết bị           

  Lịch sử                 Lưu lịch sử cảm biến,   Backend, Database,
                          điều khiển, cảnh báo,   Frontend
                          nhận diện               

  Quản lý người dùng      Đăng nhập, phân quyền,  Backend, Frontend
                          cài đặt                 

  Điều khiển giọng nói    Nhận câu lệnh qua trình Frontend, Backend
                          duyệt nếu được hỗ trợ   
  -----------------------------------------------------------------------

### Quy tắc tự động hóa dự kiến

-   Có chuyển động và ánh sáng thấp → bật đèn.
-   Không có chuyển động trong khoảng thời gian cấu hình → tắt đèn.
-   Nhiệt độ vượt ngưỡng → bật quạt.
-   Nhiệt độ giảm dưới ngưỡng tắt → tắt quạt.
-   Sự kiện an ninh phù hợp khi bật chế độ bảo vệ → gửi Telegram và có
    thể kích hoạt buzzer.

**Quy tắc an toàn logic:** - AUTO không tự ý ghi đè MANUAL, trừ chính
sách khẩn cấp được nhóm thống nhất. - Phải phân biệt `NO_FACE`,
`UNKNOWN`/độ tin cậy thấp và danh tính đã xác nhận; không coi mọi trường
hợp không khớp là người lạ đã xác minh.

------------------------------------------------------------------------

## 3. Danh sách linh kiện

### 3.1. Bo điều khiển

  Linh kiện              Số lượng dự kiến Nhiệm vụ
  -------------------- ------------------ ----------------------------------------------
  ESP32 Dev Board #1                    1 Đọc cảm biến
  ESP32 Dev Board #2                    1 Điều khiển thiết bị đầu ra
  ESP32-CAM                             1 Thu hình ảnh, thử nghiệm phát hiện/nhận diện

**Cần xác nhận model chính xác** của hai bo ESP32 và ESP32-CAM trước khi
chốt cấu hình PlatformIO. Cấu hình `esp32dev` chỉ phù hợp với một số bo
ESP32-WROOM/DevKit phổ biến, không mặc định áp dụng cho ESP32-S3/C3.

### 3.2. Cảm biến -- ESP32 #1

  Linh kiện           Số lượng Chức năng
  ----------------- ---------- --------------------------------------------------------
  DHT22                      1 Nhiệt độ và độ ẩm
  PIR HC-SR501               2 Phát hiện chuyển động
  BH1750 / GY-302            1 Đo cường độ ánh sáng (Lux)
  MC-38                      1 Phát hiện cửa đóng/mở; cần xác nhận đã lắp và kiểm tra

### 3.3. Thiết bị đầu ra -- ESP32 #2

  Linh kiện                 Số lượng dự kiến Chức năng
  ---------------------- ------------------- -----------------------
  LED                      Theo mạch thực tế Mô phỏng đèn
  Điện trở 220 Ω                 Theo số LED Hạn dòng LED
  Quạt 5V 60 × 60 mm                       1 Mô phỏng quạt
  Module MOSFET                            1 Điều khiển nguồn quạt
  Active buzzer module                     1 Âm thanh cảnh báo

### 3.4. Phụ kiện đã được đề cập

-   2 breadboard MB-102 loại 830 điểm.
-   Dây Dupont.
-   Cáp USB cấp nguồn/lập trình.
-   Nguồn 5V phù hợp cho quạt và tải ngoài.

### 3.5. Lưu ý an toàn

-   Không cấp quạt trực tiếp từ GPIO; dùng MOSFET và nguồn phù hợp.
-   Nối chung GND giữa nguồn tải và ESP32 khi mạch yêu cầu tham chiếu
    chung.
-   GPIO ESP32 không chịu được mức logic 5V; kiểm tra điện áp OUT của
    PIR.
-   DHT22 dạng cảm biến rời thường cần điện trở kéo lên DATA 4.7--10 kΩ;
    module có thể đã tích hợp.
-   Không đưa điện lưới trực tiếp lên breadboard hoặc ESP32.
-   Kiểm tra đúng cực VCC/GND và sơ đồ chân của module trước khi cấp
    nguồn.

------------------------------------------------------------------------

## 4. GPIO và tình trạng phần cứng

### 4.1. ESP32 #1 -- Sensor Node

Bảng chân đã được đề cập trước đó:

  Linh kiện   Chân tín hiệu     GPIO
  ----------- --------------- ------
  BH1750      SDA                 21
  BH1750      SCL                 22
  MC-38       Signal              25
  DHT22       DATA                27
  PIR #1      OUT                 32
  PIR #2      OUT                 33

Đây là **sơ đồ dự kiến**, cần đối chiếu với dây đang cắm trên mạch trước
khi nạp firmware. MC-38 chỉ đưa vào firmware khi đã lắp và kiểm tra.

Nếu MC-38 được đấu giữa GPIO25 và GND, dùng `INPUT_PULLUP`, tiếp điểm
thường cho LOW khi đóng và HIGH khi mở. Phải kiểm tra thực tế và thống
nhất quy ước `door_open`.

### 4.2. ESP32 #2 -- Control Node

Các thiết bị cần điều khiển: - LED: bật/tắt. - Quạt 5V qua module
MOSFET: bật/tắt. - Active buzzer: bật/tắt.

**GPIO ESP32 #2 chưa được chốt.** Ghi lại pinout thực tế sau khi kiểm
tra mạch; không tự lấy GPIO của ESP32 #1 hoặc nạp pinout phỏng đoán.

### 4.3. ESP32-CAM

-   Xác nhận đúng model bo.
-   Kiểm tra camera khởi tạo và chụp ảnh.
-   Sau đó mới thử phát hiện/nhận diện khuôn mặt.
-   Chưa chốt GPIO và thư viện camera trước khi biết model.

**Phương án AI chưa chốt:** Khả năng nhận diện trực tiếp phụ thuộc
model, RAM/PSRAM và thư viện. Cần thử nghiệm sớm. Nếu bo không đủ tài
nguyên, cân nhắc để ESP32-CAM thu hình/gửi ảnh và xử lý AI trên máy
tính/Backend.

------------------------------------------------------------------------

## 5. Kiến trúc hệ thống

``` text
ESP32 #1 (cảm biến) ──MQTT──► Mosquitto ──► Backend FastAPI ──► Database
                                     ▲             │
                                     │             ├──REST API──► Frontend React
                                     │             │
ESP32 #2 (đèn/quạt/còi) ◄──MQTT──────┘             └──► Telegram Bot
       │
       └── ACK / Status ───────────► Mosquitto ──► Backend

ESP32-CAM ── sự kiện/ảnh ──────────► Backend
```

### Luồng dữ liệu cảm biến

1.  ESP32 #1 đọc cảm biến.
2.  Firmware tạo JSON.
3.  ESP32 #1 publish MQTT.
4.  Backend subscribe, kiểm tra và lưu Database.
5.  Frontend gọi API để hiển thị.

### Luồng điều khiển

1.  Người dùng thao tác trên Frontend.
2.  Frontend gửi request đến Backend.
3.  Backend kiểm tra quyền và publish MQTT command.
4.  ESP32 #2 nhận lệnh, điều khiển GPIO.
5.  ESP32 #2 gửi ACK và status.
6.  Backend cập nhật Database; Frontend hiển thị kết quả đã xác nhận.

**MQTT publish thành công không đồng nghĩa thiết bị đã bật/tắt thành
công.** Phải chờ ACK/status từ ESP32.

------------------------------------------------------------------------

## 6. Công nghệ dự kiến

  Thành phần       Công nghệ                        Mục đích
  ---------------- -------------------------------- ---------------------------
  Firmware         PlatformIO + Arduino Framework   Build/nạp firmware ESP32
  Cảm biến         DHT library, Adafruit BH1750     Đọc DHT22 và BH1750
  MQTT firmware    PubSubClient                     Gửi/nhận MQTT
  JSON firmware    ArduinoJson                      Đóng gói/giải mã JSON
  Backend          Python 3 + FastAPI               REST API và nghiệp vụ
  MQTT Broker      Mosquitto                        Trung chuyển message
  MQTT Backend     Paho-MQTT                        Backend publish/subscribe
  Database         SQLite ban đầu                   Lưu dữ liệu
  ORM              SQLAlchemy                       Truy vấn Database
  Authentication   JWT                              Xác thực
  Notification     Telegram Bot API                 Gửi cảnh báo
  Frontend         React + Vite + TypeScript        Giao diện Web
  Styling          Tailwind CSS                     Giao diện
  HTTP client      Axios                            Gọi API
  Routing          React Router                     Điều hướng
  Charts           Recharts                         Biểu đồ
  Voice            Web Speech API                   Nhận câu lệnh trình duyệt
  Deployment       Docker Compose (dự kiến)         Chạy Backend và Broker

------------------------------------------------------------------------

## 7. Giao thức MQTT đề xuất

Các topic sau là **đề xuất cần nhóm thống nhất**, chưa phải cấu hình đã
kiểm thử:

  ----------------------------------------------------------------------------------
  Topic                              Hướng                   Nội dung
  ---------------------------------- ----------------------- -----------------------
  `smarthome/sensor/node1`           ESP32 #1 → Backend      Dữ liệu cảm biến

  `smarthome/device/node2/command`   Backend → ESP32 #2      Lệnh điều khiển

  `smarthome/device/node2/status`    ESP32 #2 → Backend      Trạng thái thiết bị

  `smarthome/device/node2/ack`       ESP32 #2 → Backend      Kết quả thực hiện lệnh

  `smarthome/security/recognition`   ESP32-CAM/AI → Backend  Sự kiện nhận diện

  `smarthome/system/node1/status`    ESP32 #1 → Backend      Trạng thái node

  `smarthome/system/node2/status`    ESP32 #2 → Backend      Trạng thái node
  ----------------------------------------------------------------------------------

### 7.1. JSON cảm biến mẫu

``` json
{
  "device_id": "esp32_sensor_01",
  "temperature": 28.5,
  "humidity": 65.2,
  "light_lux": 120.5,
  "pir_1": true,
  "pir_2": false,
  "door_open": null,
  "timestamp": "2026-11-06T09:30:00Z"
}
```

Số liệu trên chỉ minh họa. `door_open: null` nghĩa là chưa có dữ liệu
cửa, không phải cửa đang mở hay đóng.

### 7.2. JSON lệnh điều khiển mẫu

``` json
{
  "command_id": "cmd_0001",
  "device_id": "light_1",
  "state": "ON",
  "mode": "MANUAL"
}
```

### 7.3. JSON ACK mẫu

``` json
{
  "command_id": "cmd_0001",
  "device_id": "light_1",
  "state": "ON",
  "success": true
}
```

### 7.4. JSON sự kiện nhận diện mẫu

``` json
{
  "event_id": "recognition_0001",
  "person_name": "unknown",
  "identity": "UNKNOWN",
  "confidence": 0.51,
  "timestamp": "2026-11-06T09:31:00Z"
}
```

Đây là dữ liệu minh họa. Nhóm cần định nghĩa trạng thái `KNOWN`,
`UNKNOWN`, `NO_FACE` và ngưỡng confidence. Không tự gán `STRANGER` cho
mọi trường hợp không khớp.

------------------------------------------------------------------------

## 8. API Backend dự kiến

  Method   Endpoint                       Chức năng
  -------- ------------------------------ -------------------------------
  POST     `/api/auth/login`              Đăng nhập
  GET      `/api/auth/me`                 Thông tin tài khoản hiện tại
  GET      `/api/sensors/latest`          Dữ liệu cảm biến mới nhất
  GET      `/api/sensors/history`         Lịch sử cảm biến
  GET      `/api/devices`                 Danh sách thiết bị/trạng thái
  POST     `/api/devices/control`         Gửi lệnh điều khiển
  GET      `/api/alerts`                  Danh sách cảnh báo
  GET      `/api/recognitions`            Lịch sử nhận diện
  GET      `/api/automation/rules`        Danh sách quy tắc
  POST     `/api/automation/rules`        Tạo quy tắc
  PUT      `/api/automation/rules/{id}`   Cập nhật quy tắc
  GET      `/api/settings`                Lấy cấu hình
  PUT      `/api/settings`                Cập nhật cấu hình

Backend và Frontend cần thống nhất schema request/response, mã lỗi, xác
thực và phân quyền trước khi tích hợp.

------------------------------------------------------------------------

## 9. Phân công nhiệm vụ 3 thành viên

### Thành viên 1 -- Hardware & Embedded Developer (bạn)

**Phạm vi:** Lắp ráp/kiểm tra phần cứng, PlatformIO, firmware các node,
camera/AI phía thiết bị và tích hợp phần cứng.

**Phần cứng** - Kiểm tra model bo, nguồn, GND và sơ đồ dây. - Đối chiếu
GPIO thực tế. - Kiểm tra cảm biến và thiết bị đầu ra. - Ghi lại sơ đồ
đấu nối.

**ESP32 #1** - Tạo project PlatformIO. - Đọc DHT22, BH1750, hai PIR và
MC-38 nếu đã lắp. - Kiểm tra bằng Serial Monitor. - Kết nối Wi-Fi. -
Publish JSON qua MQTT. - Xử lý mất kết nối/reconnect.

**ESP32 #2** - Tạo project PlatformIO. - Kiểm tra LED, MOSFET/quạt,
buzzer. - Viết hàm bật/tắt thiết bị. - Subscribe MQTT command. - Giải mã
JSON, thực hiện lệnh. - Publish ACK/status. - Đưa đầu ra về trạng thái
an toàn khi khởi động theo thiết kế.

**ESP32-CAM** - Xác nhận model. - Khởi tạo camera, chụp ảnh. - Thử phát
hiện và nhận diện. - Phân biệt không có mặt, chưa xác định và danh tính
được xác nhận. - Gửi sự kiện/ảnh theo phương án nhóm thống nhất. - Đề
xuất xử lý AI trên Backend nếu phần cứng không đủ tài nguyên.

**Bàn giao** - Source code ba project firmware. - Bảng GPIO và sơ đồ dây
thực tế. - MQTT topic/JSON đã thống nhất. - Log hoặc ảnh kiểm thử. -
Phối hợp kiểm thử luồng dữ liệu và điều khiển end-to-end.

### Thành viên 2 -- Backend Developer

**Phạm vi:** FastAPI, Database, MQTT phía Backend, xác thực, tự động hóa
và Telegram.

**Task** 1. Khởi tạo Python/FastAPI, cấu trúc source, CORS,
`requirements.txt`. 2. Thiết kế Database: Users, Devices, SensorHistory,
DeviceHistory, Alerts, Recognitions, AutomationRules. 3. Cài Mosquitto
và viết Paho-MQTT Subscriber/Publisher. 4. Nhận JSON cảm biến, validate
và lưu Database. 5. Gửi MQTT command, nhận ACK/status, xử lý
timeout/lỗi. 6. Xây dựng JWT, đăng nhập và phân quyền. 7. Xây dựng REST
API theo danh sách ở mục 8. 8. Xây dựng quy tắc AUTO, giữ đúng ưu tiên
MANUAL/AUTO. 9. Tích hợp Telegram Bot và lưu lịch sử cảnh báo.

**Bàn giao** - Source code `backend/`. - Database/schema. - FastAPI và
MQTT hoạt động. - API đã kiểm thử. - Telegram Bot thử nghiệm. -
`API_SPEC.md` và README hướng dẫn chạy.

**Có thể bắt đầu ngay:** dựng FastAPI, Database, Mosquitto, API mẫu và
test MQTT bằng JSON giả lập; sau đó thay bằng dữ liệu thật từ firmware.

### Thành viên 3 -- Frontend Developer

**Phạm vi:** React Web, Dashboard, điều khiển, lịch sử và trang quản lý.

**Task** 1. Tạo React + Vite + TypeScript, Tailwind, Router, Axios. 2.
Dựng layout, sidebar, header và responsive cơ bản. 3. Làm Login và xử lý
phiên đăng nhập. 4. Làm Dashboard hiển thị nhiệt độ, độ ẩm, Lux, PIR,
cửa và trạng thái thiết bị. 5. Làm giao diện bật/tắt đèn, quạt, còi và
AUTO/MANUAL. 6. Làm trang cấu hình Automation. 7. Làm trang AI Security
và lịch sử nhận diện. 8. Làm lịch sử cảm biến, điều khiển, cảnh báo và
biểu đồ Recharts. 9. Làm quản lý người dùng/cài đặt theo API. 10. Thử
nghiệm điều khiển giọng nói bằng Web Speech API nếu trình duyệt hỗ trợ.

**Bàn giao** - Source code `frontend/`. - Các trang giao diện. - Tích
hợp API. - Biểu đồ/lịch sử và điều khiển. - README hướng dẫn chạy.

**Có thể bắt đầu ngay:** dùng Mock Data/JSON để dựng giao diện, tách API
service để thay dữ liệu mẫu bằng API thật khi Backend sẵn sàng.

------------------------------------------------------------------------

## 10. Việc cần làm ngay

### 10.1. Bạn -- ưu tiên phần cứng và firmware

**Bước 1: Xác nhận phần cứng** - \[ \] Ghi model chính xác ESP32 #1. -
\[ \] Ghi model chính xác ESP32 #2. - \[ \] Ghi model ESP32-CAM. - \[ \]
Đối chiếu GPIO với dây thực tế. - \[ \] Xác nhận MC-38 đã lắp hay
chưa. - \[ \] Kiểm tra nguồn và GND.

**Bước 2: ESP32 #1** - \[ \] Tạo project PlatformIO. - \[ \] Build và
upload firmware. - \[ \] Kiểm tra DHT22. - \[ \] Kiểm tra BH1750. - \[
\] Kiểm tra PIR #1 và PIR #2. - \[ \] Kiểm tra MC-38 nếu đã lắp. - \[ \]
Kết nối Wi-Fi. - \[ \] Publish JSON MQTT. - \[ \] Xác nhận Backend nhận
được dữ liệu.

**Bước 3: ESP32 #2** - \[ \] Tạo project PlatformIO. - \[ \] Test LED. -
\[ \] Test quạt qua MOSFET. - \[ \] Test buzzer. - \[ \] Kết nối
Wi-Fi/MQTT. - \[ \] Nhận command. - \[ \] Gửi ACK/status.

**Bước 4: ESP32-CAM** - \[ \] Xác nhận model. - \[ \] Khởi tạo camera và
chụp ảnh. - \[ \] Thử phát hiện khuôn mặt. - \[ \] Đánh giá phương án
nhận diện. - \[ \] Chốt cách gửi sự kiện về Backend.

**Ưu tiên tích hợp:** Hoàn thiện luồng ESP32 #1 → MQTT → Backend và
Backend → MQTT → ESP32 #2 trước. Không cần chờ AI hoàn thiện mới tích
hợp hai luồng này.

### 10.2. Thành viên 2 -- Backend

-   [ ] Tạo project FastAPI.
-   [ ] Tạo cấu trúc thư mục.
-   [ ] Cài và chạy Mosquitto.
-   [ ] Tạo schema Database ban đầu.
-   [ ] Tạo API mẫu.
-   [ ] Viết MQTT Subscriber/Publisher.
-   [ ] Test bằng JSON mẫu và MQTT client độc lập.
-   [ ] Thống nhất topic/schema/QoS/ACK với bạn.
-   [ ] Hoàn thiện tích hợp khi firmware gửi dữ liệu thật.

### 10.3. Thành viên 3 -- Frontend

-   [ ] Tạo React + Vite + TypeScript.
-   [ ] Dựng layout tổng thể.
-   [ ] Làm Login.
-   [ ] Làm Dashboard bằng dữ liệu mẫu.
-   [ ] Làm giao diện điều khiển thiết bị.
-   [ ] Làm AUTO/MANUAL và Automation.
-   [ ] Làm AI Security.
-   [ ] Làm lịch sử và biểu đồ.
-   [ ] Chuẩn bị API service để kết nối Backend.

------------------------------------------------------------------------

## 11. Thứ tự tích hợp và mốc hoàn thành

  Mốc   Công việc                    Kết quả
  ----- ---------------------------- ---------------------------------------
  M1    Kiểm kê phần cứng/GPIO       Sơ đồ mạch thực tế
  M2    Firmware đọc cảm biến        ESP32 #1 đọc ổn định
  M3    Backend + Mosquitto cơ bản   Nhận message thử nghiệm
  M4    ESP32 #1 gửi MQTT            Dữ liệu thật vào Backend
  M5    ESP32 #2 điều khiển MQTT     Nhận lệnh, trả ACK/status
  M6    Frontend kết nối API         Dashboard/điều khiển hoạt động
  M7    Camera/AI                    Sự kiện camera/AI được gửi về Backend
  M8    Automation/Telegram          Tự động hóa và cảnh báo hoạt động
  M9    Kiểm thử end-to-end          Demo toàn hệ thống

Các mốc là thứ tự công việc, không phải ngày cố định; nhóm tự điều chỉnh
theo hạn nộp.

------------------------------------------------------------------------

## 12. Git và quản lý source code

Cấu trúc repository đề xuất:

``` text
smart-home-iot/
├── firmware/
│   ├── esp32-sensor-node/
│   ├── esp32-control-node/
│   └── esp32-cam/
├── backend/
├── frontend/
├── docs/
│   ├── SYSTEM_ARCHITECTURE.md
│   ├── MQTT_SPEC.md
│   └── API_SPEC.md
├── docker-compose.yml
└── README.md
```

Branch: - `main`: bản ổn định. - `develop`: nhánh tích hợp. -
`feature/firmware`: thành viên 1. - `feature/backend`: thành viên 2. -
`feature/frontend`: thành viên 3.

Quy trình: cập nhật `develop` → làm trên branch cá nhân → commit/push →
tạo Pull Request về `develop` → review/test → merge. Chỉ đưa `develop`
vào `main` khi tích hợp ổn định.

Không commit Wi-Fi password, MQTT password, Telegram Bot Token hoặc JWT
secret lên GitHub. Dùng file cấu hình riêng và `.gitignore`.

------------------------------------------------------------------------

## 13. Tiêu chí nghiệm thu

### Firmware/phần cứng

-   [ ] ESP32 #1 đọc đúng các cảm biến đã lắp.
-   [ ] ESP32 #1 gửi MQTT theo schema.
-   [ ] ESP32 #2 điều khiển đúng LED/quạt/buzzer.
-   [ ] ESP32 #2 gửi ACK/status.
-   [ ] ESP32-CAM khởi tạo và lấy được ảnh.
-   [ ] Cảm biến chưa lắp/lỗi được biểu diễn đúng, không tạo dữ liệu
    giả.

### Backend

-   [ ] FastAPI chạy được.
-   [ ] Database lưu được dữ liệu.
-   [ ] MQTT Subscriber nhận dữ liệu.
-   [ ] MQTT Publisher gửi lệnh.
-   [ ] Backend nhận ACK/status.
-   [ ] Đăng nhập/phân quyền hoạt động.
-   [ ] Automation và Telegram hoạt động thử nghiệm.

### Frontend

-   [ ] Login/logout hoạt động.
-   [ ] Dashboard hiển thị dữ liệu Backend.
-   [ ] Điều khiển thiết bị qua Backend.
-   [ ] Trạng thái hiển thị theo ACK/status.
-   [ ] Biểu đồ và lịch sử hiển thị.
-   [ ] Trang AI Security và cài đặt hiển thị dữ liệu.

### End-to-end

-   [ ] Dữ liệu cảm biến thật xuất hiện trên Dashboard.
-   [ ] Lệnh bật/tắt từ Web tác động lên thiết bị thật.
-   [ ] Backend ghi lịch sử lệnh và trạng thái.
-   [ ] Sự kiện an ninh thử nghiệm được lưu và cảnh báo đúng cấu hình.

------------------------------------------------------------------------

## 14. Các thông tin còn cần nhóm xác nhận

  Nội dung                   Trạng thái
  -------------------------- --------------------------------------
  Model ESP32 #1             Cần xác nhận
  Model ESP32 #2             Cần xác nhận
  Model ESP32-CAM            Cần xác nhận
  GPIO ESP32 #1              Có sơ đồ dự kiến; cần đối chiếu mạch
  GPIO ESP32 #2              Chưa chốt
  MC-38 đã lắp/kiểm tra      Cần xác nhận
  MQTT topics và JSON        Có đề xuất; cần thống nhất
  QoS, retain, ACK/timeout   Cần thống nhất
  Nơi xử lý AI               Cần thử nghiệm
  API request/response       Backend và Frontend cần thống nhất
  IP máy chạy Mosquitto      Cần xác định khi triển khai

------------------------------------------------------------------------

## 15. Lưu ý khi chạy hệ thống

-   ESP32 kết nối đến IP LAN của máy chạy Mosquitto; không dùng
    `localhost` để trỏ từ ESP32 về máy tính.
-   Cấu hình firewall và xác thực MQTT; không mở Broker không bảo vệ ra
    mạng công cộng.
-   Frontend gọi Backend API, không truy cập Database trực tiếp.
-   ESP32 giao tiếp với Backend qua MQTT Broker.
-   Firmware cần reconnect khi mất Wi-Fi/MQTT và không chặn vòng lặp đọc
    cảm biến quá lâu.
-   Dữ liệu cảm biến lỗi/chưa lắp phải là `null` hoặc trạng thái lỗi phù
    hợp, không tự tạo số đo.
-   Lưu log để dễ debug.

Lệnh PlatformIO thường dùng:

``` bash
# Build
pio run

# Upload firmware
pio run -t upload

# Serial Monitor
pio device monitor -b 115200
```

`pio test` dùng để chạy unit test đã được tạo, không phải lệnh nạp
firmware thông thường.

------------------------------------------------------------------------

## 16. Kết luận -- ưu tiên hiện tại

-   **Bạn:** phần cứng, kiểm tra linh kiện, PlatformIO, firmware ESP32
    #1/#2, ESP32-CAM và tích hợp thiết bị.
-   **Thành viên 2:** FastAPI, Database, MQTT phía Backend, xác thực, tự
    động hóa và Telegram.
-   **Thành viên 3:** React Frontend, Dashboard, điều khiển Web, lịch
    sử, biểu đồ và trang quản lý.

**Việc ưu tiên của bạn ngay lúc này:** 1. Xác nhận model bo mạch và sơ
đồ dây thực tế. 2. Hoàn thiện firmware đọc cảm biến ESP32 #1. 3. Kiểm
tra từng cảm biến bằng Serial Monitor. 4. Kết nối Wi-Fi và gửi JSON
MQTT. 5. Làm firmware điều khiển ESP32 #2. 6. Kiểm tra camera và đánh
giá phương án AI.

Trong lúc đó, Backend có thể dựng bằng message mẫu và Frontend có thể
dùng Mock Data. Khi firmware có dữ liệu thật, cả nhóm tích hợp theo
topic và schema đã thống nhất.

**Nguyên tắc:** Mỗi thành viên chịu trách nhiệm một phần, bàn giao bằng
source code và kết quả kiểm thử; không đợi toàn bộ dự án hoàn thành mới
tích hợp.
