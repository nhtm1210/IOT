"""
Bộ kiểm thử tự động (End-to-End API & Integration Tests) cho Backend Smart Home IoT AI.
Chạy lệnh:
    pytest -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def test_full_backend_workflow():
    with TestClient(app) as client:
        # 1. Health Check
        r_health = client.get("/api/health")
        assert r_health.status_code == 200
        assert r_health.json()["status"] == "ok"

        # 2. Auth Login (JSON) với tài khoản admin mặc định
        r_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert r_login.status_code == 200, r_login.text
        token_data = r_login.json()
        admin_token = token_data["access_token"]
        assert token_data["user"]["role"] == "ADMIN"

        headers_admin = {"Authorization": f"Bearer {admin_token}"}

        # 3. Kiểm tra /api/auth/me
        r_me = client.get("/api/auth/me", headers=headers_admin)
        assert r_me.status_code == 200
        assert r_me.json()["username"] == "admin"

        # 4. Kiểm tra RBAC: Tài khoản GUEST không được phép điều khiển thiết bị (403 Forbidden)
        r_guest_login = client.post(
            "/api/auth/login",
            json={"username": "guest", "password": "guest123"},
        )
        assert r_guest_login.status_code == 200
        guest_token = r_guest_login.json()["access_token"]
        r_guest_ctrl = client.post(
            "/api/devices/control",
            json={"device_id": "fan_1", "state": "ON", "mode": "MANUAL"},
            headers={"Authorization": f"Bearer {guest_token}"},
        )
        assert r_guest_ctrl.status_code == 403

        # 5. Kiểm tra /api/mqtt/state & /api/sensors/latest & /api/sensors/history
        r_state = client.get("/api/mqtt/state")
        assert r_state.status_code == 200
        state_json = r_state.json()
        assert "esp32_cluster1" in state_json["nodes"]
        assert "esp32_cluster2" in state_json["nodes"]
        assert "esp32_cam_01" in state_json["nodes"]

        r_latest = client.get("/api/sensors/latest")
        assert r_latest.status_code == 200
        assert "summary" in r_latest.json()

        r_hist = client.get("/api/sensors/history?limit=10")
        assert r_hist.status_code == 200
        assert len(r_hist.json()) >= 1

        # 6. Kiểm tra điều khiển 3 cụm qua /api/mqtt/* và /api/devices/control
        r_c1 = client.post(
            "/api/mqtt/cluster1/control",
            json={"mode": "MANUAL", "light": True, "buzzer": False},
            headers=headers_admin,
        )
        assert r_c1.status_code == 200
        assert r_c1.json()["node"]["outputs"]["light"] is True

        r_c2 = client.post(
            "/api/mqtt/cluster2/control",
            json={"mode": "MANUAL", "light": True, "fan": True},
            headers=headers_admin,
        )
        assert r_c2.status_code == 200
        assert r_c2.json()["node"]["outputs"]["fan"] is True

        r_dev_ctrl = client.post(
            "/api/devices/control",
            json={"device_id": "fan_1", "state": "OFF", "mode": "MANUAL"},
            headers=headers_admin,
        )
        assert r_dev_ctrl.status_code == 200
        assert r_dev_ctrl.json()["node"]["outputs"]["fan"] is False

        r_devs = client.get("/api/devices")
        assert r_devs.status_code == 200
        assert len(r_devs.json()["devices"]) == 5

        # 7. Kiểm tra Enroll mẫu mặt chủ nhà & Nhận diện mở cửa Servo SG90
        fake_owner_jpeg = b"\xff\xd8\xff\xe0" + b"OWNER_FACE_TEMPLATE_BYTES_2026" * 10 + b"\xff\xd9"
        r_enroll = client.post(
            "/api/security/recognize",
            content=fake_owner_jpeg,
            headers={
                "Content-Type": "image/jpeg",
                "X-Device-Id": "esp32_cam_01",
                "X-Event-Id": "test_enroll_01",
                "X-Mode": "ENROLL_OWNER",
                "X-Person-Name": "Chu_Nha",
            },
        )
        assert r_enroll.status_code == 200
        assert r_enroll.json()["status"] == "enrolled"

        # Nhận diện với đúng ảnh chủ nhà -> KNOWN, authorized=True, action="OPEN", servo_angle_deg=90
        r_rec_known = client.post(
            "/api/security/recognize",
            content=fake_owner_jpeg,
            headers={
                "Content-Type": "image/jpeg",
                "X-Device-Id": "esp32_cam_01",
                "X-Event-Id": "test_rec_known_01",
            },
        )
        assert r_rec_known.status_code == 200
        rec_data = r_rec_known.json()
        assert rec_data["identity"] == "KNOWN"
        assert rec_data["authorized"] is True
        assert rec_data["action"] == "OPEN"
        assert rec_data["servo_angle_deg"] == 90

        # Nhận diện với ảnh người lạ (MOCK_IDENTITY=UNKNOWN) -> UNKNOWN, action="KEEP_LOCKED", servo=0 + tạo Alert CRITICAL
        os.environ["MOCK_IDENTITY"] = "UNKNOWN"
        try:
            r_rec_unknown = client.post(
                "/api/security/recognize",
                content=b"\xff\xd8\xff\xe0" + b"STRANGER_BYTES" * 10 + b"\xff\xd9",
                headers={
                    "Content-Type": "image/jpeg",
                    "X-Device-Id": "esp32_cam_01",
                    "X-Event-Id": "test_rec_unknown_01",
                },
            )
            assert r_rec_unknown.status_code == 200
            unk_data = r_rec_unknown.json()
            assert unk_data["identity"] == "UNKNOWN"
            assert unk_data["authorized"] is False
            assert unk_data["action"] == "KEEP_LOCKED"
            assert unk_data["servo_angle_deg"] == 0
        finally:
            os.environ.pop("MOCK_IDENTITY", None)

        # Kiểm tra danh sách lịch sử nhận diện
        r_recs = client.get("/api/recognitions")
        assert r_recs.status_code == 200
        assert len(r_recs.json()) >= 2

        # 8. Kiểm tra Automation Rules & đồng bộ Settings
        r_rules = client.get("/api/automation/rules")
        assert r_rules.status_code == 200
        rules = r_rules.json()
        assert len(rules) >= 4

        r_settings = client.put(
            "/api/settings",
            json={"temp_threshold_c": 29.5, "humidity_threshold_pct": 42.0},
            headers=headers_admin,
        )
        assert r_settings.status_code == 200
        assert r_settings.json()["temp_threshold_c"] == 29.5

        # 9. Kiểm tra Alerts
        r_alerts = client.get("/api/alerts")
        assert r_alerts.status_code == 200
        assert r_alerts.json()["count"] >= 1

        # 10. Kiểm tra WebSocket /ws/dashboard
        with client.websocket_connect("/ws/dashboard") as ws:
            init_msg = ws.receive_json()
            assert init_msg["event"] == "INITIAL_STATE"
            assert "esp32_cluster1" in init_msg["data"]["nodes"]
            ws.send_text("ping")
            pong_msg = ws.receive_json()
            assert pong_msg["event"] == "PONG"

    # Dọn dẹp file ảnh tạm sinh ra trong quá trình chạy test
    for tmp_file in [
        BACKEND_DIR / "data" / "captured_events" / "test_rec_known_01.jpg",
        BACKEND_DIR / "data" / "captured_events" / "test_rec_unknown_01.jpg",
        BACKEND_DIR / "data" / "owner_faces" / "owner.jpg",
    ]:
        if tmp_file.exists():
            tmp_file.unlink()


if __name__ == "__main__":
    test_full_backend_workflow()
    print("ALL_BACKEND_TESTS_PASSED!")
