"""
API Cảnh báo & Cài đặt hệ thống (`/api/alerts/*`, `/api/settings/*`).
Bao gồm tích hợp kiểm tra kết nối Telegram Bot (`/api/settings/telegram/test`).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operator
from app.models.models import Alert, AutomationRule, SystemSetting
from app.schemas.schemas import AlertOut, SettingsUpdateRequest, TelegramTestRequest
from app.services.telegram_bot import telegram_service
from app.websocket.manager import ws_manager

router = APIRouter(tags=["7. Alerts, Settings & Telegram"])


@router.get(
    "/api/alerts",
    summary="Danh sách cảnh báo an ninh & môi trường (kèm số lượng chưa đọc)",
)
def list_alerts(
    unread_only: bool = Query(default=False),
    severity: Optional[str] = Query(default=None, description="INFO | WARNING | CRITICAL"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    query = db.query(Alert)
    if unread_only:
        query = query.filter(Alert.is_read.is_(False))
    if severity:
        query = query.filter(Alert.severity == severity.upper())

    items = query.order_by(Alert.id.desc()).limit(limit).all()
    unread_count = db.query(Alert).filter(Alert.is_read.is_(False)).count()

    return {
        "unread_count": unread_count,
        "count": len(items),
        "items": [AlertOut.model_validate(a).model_dump() for a in items],
    }


@router.put(
    "/api/alerts/{alert_id}/read",
    response_model=AlertOut,
    summary="Đánh dấu 1 cảnh báo là đã đọc",
)
def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db),
) -> Any:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    alert.is_read = True
    db.commit()
    db.refresh(alert)
    return alert


@router.post(
    "/api/alerts/read-all",
    summary="Đánh dấu toàn bộ cảnh báo là đã đọc",
)
def mark_all_alerts_read(db: Session = Depends(get_db)) -> Dict[str, Any]:
    updated = db.query(Alert).filter(Alert.is_read.is_(False)).update({"is_read": True})
    db.commit()
    return {"status": "ok", "marked_read": updated}


def _build_settings_dict(db: Session) -> Dict[str, Any]:
    rows = {r.key: r.value for r in db.query(SystemSetting).all()}

    def _as_float(key: str, default: float) -> float:
        try:
            return float(rows.get(key, default))
        except Exception:
            return default

    def _as_int(key: str, default: int) -> int:
        try:
            return int(float(rows.get(key, default)))
        except Exception:
            return default

    def _as_bool(key: str, default: bool) -> bool:
        val = str(rows.get(key, str(default))).lower()
        return val in ("true", "1", "yes")

    return {
        "temp_threshold_c": _as_float("temp_threshold_c", 30.0),
        "humidity_threshold_pct": _as_float("humidity_threshold_pct", 40.0),
        "light_adc_threshold": _as_int("light_adc_threshold", 2000),
        "pir_hold_seconds": _as_int("pir_hold_seconds", 5),
        "face_match_threshold": _as_float("face_match_threshold", 0.65),
        "door_open_seconds": _as_int("door_open_seconds", 5),
        "security_armed": _as_bool("security_armed", True),
        "telegram_enabled": _as_bool("telegram_enabled", False),
        "telegram_bot_token": rows.get("telegram_bot_token", ""),
        "telegram_chat_id": rows.get("telegram_chat_id", ""),
    }


@router.get(
    "/api/settings",
    summary="Lấy toàn bộ cấu hình ngưỡng cảm biến, nhận diện AI & Telegram Bot",
)
def get_settings(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return _build_settings_dict(db)


@router.put(
    "/api/settings",
    summary="Cập nhật cấu hình hệ thống & tự động đồng bộ sang Automation Rules",
)
def update_settings(
    req: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_operator),
) -> Dict[str, Any]:
    updates = req.model_dump(exclude_none=True)

    for key, val in updates.items():
        if isinstance(val, bool):
            str_val = "true" if val else "false"
        else:
            str_val = str(val)

        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if row:
            row.value = str_val
        else:
            db.add(SystemSetting(key=key, value=str_val, description=""))

    # Đồng bộ ngược sang 4 kịch bản tự động hóa để giao diện /automation hiển thị đúng ngưỡng mới
    def _update_rule_cfg(code: str, patch: Dict[str, Any]) -> None:
        rule = db.query(AutomationRule).filter(AutomationRule.code == code).first()
        if rule:
            cfg = rule.get_config()
            cfg.update(patch)
            rule.config_json = json.dumps(cfg, ensure_ascii=False)

    if "pir_hold_seconds" in updates:
        _update_rule_cfg("RULE_C1_PIR_ALARM", {"hold_seconds": updates["pir_hold_seconds"]})
    if "temp_threshold_c" in updates or "humidity_threshold_pct" in updates:
        patch = {}
        if "temp_threshold_c" in updates:
            patch["temp_threshold_c"] = updates["temp_threshold_c"]
        if "humidity_threshold_pct" in updates:
            patch["humidity_max_pct"] = updates["humidity_threshold_pct"]
        _update_rule_cfg("RULE_C2_TEMP_HUM_FAN", patch)
    if "light_adc_threshold" in updates:
        _update_rule_cfg(
            "RULE_C2_LIGHT_LDR", {"light_adc_threshold": updates["light_adc_threshold"]}
        )
    if "face_match_threshold" in updates or "door_open_seconds" in updates:
        patch = {}
        if "face_match_threshold" in updates:
            patch["confidence_threshold"] = updates["face_match_threshold"]
        if "door_open_seconds" in updates:
            patch["open_duration_sec"] = updates["door_open_seconds"]
        _update_rule_cfg("RULE_CAM_FACE_DOOR", patch)

    db.commit()
    new_settings = _build_settings_dict(db)
    ws_manager.broadcast_threadsafe("SETTINGS_UPDATED", new_settings)
    return new_settings


@router.post(
    "/api/settings/telegram/test",
    summary="Gửi tin nhắn thử nghiệm qua Telegram Bot",
)
def test_telegram_notification(
    req: TelegramTestRequest,
    _user=Depends(require_operator),
) -> Dict[str, Any]:
    ok, detail = telegram_service.send_message_sync(
        text=req.message,
        bot_token=req.bot_token,
        chat_id=req.chat_id,
        force=True,
    )
    return {"success": ok, "detail": detail}
