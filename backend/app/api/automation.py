"""
API Quản lý Kịch bản Tự động hóa (`/api/automation/rules`).
Phục vụ màn hình `/automation` trên Web Dashboard (4 kịch bản chuẩn của 3 cụm ESP32 + hỗ trợ tạo mới/cập nhật).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operator
from app.models.models import AutomationRule, SystemSetting
from app.schemas.schemas import (
    AutomationRuleCreateRequest,
    AutomationRuleOut,
    AutomationRuleUpdateRequest,
)
from app.websocket.manager import ws_manager

router = APIRouter(tags=["6. Automation Rules"])


def _rule_to_out(rule: AutomationRule) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "code": rule.code,
        "name": rule.name,
        "cluster_id": rule.cluster_id,
        "description": rule.description,
        "is_enabled": rule.is_enabled,
        "config": rule.get_config(),
        "updated_at": rule.updated_at,
    }


def _sync_rule_config_to_settings(db: Session, rule: AutomationRule) -> None:
    """Đồng bộ các ngưỡng trong rule với bảng SystemSetting để hai màn hình /automation và /settings luôn khớp nhau."""
    cfg = rule.get_config()
    mapping = {
        "temp_threshold_c": "temp_threshold_c",
        "humidity_max_pct": "humidity_threshold_pct",
        "light_adc_threshold": "light_adc_threshold",
        "hold_seconds": "pir_hold_seconds",
        "confidence_threshold": "face_match_threshold",
        "open_duration_sec": "door_open_seconds",
    }
    for cfg_key, setting_key in mapping.items():
        if cfg_key in cfg and cfg[cfg_key] is not None:
            row = db.query(SystemSetting).filter(SystemSetting.key == setting_key).first()
            if row:
                row.value = str(cfg[cfg_key])


@router.get(
    "/api/automation/rules",
    response_model=List[AutomationRuleOut],
    summary="Danh sách các quy tắc / kịch bản tự động hóa của 3 cụm ESP32",
)
def list_automation_rules(db: Session = Depends(get_db)) -> Any:
    rules = db.query(AutomationRule).order_by(AutomationRule.id.asc()).all()
    return [_rule_to_out(r) for r in rules]


@router.post(
    "/api/automation/rules",
    response_model=AutomationRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo quy tắc tự động hóa mới",
)
def create_automation_rule(
    req: AutomationRuleCreateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_operator),
) -> Any:
    code = (req.code or f"RULE_CUSTOM_{uuid.uuid4().hex[:6]}").upper()
    existing = db.query(AutomationRule).filter(AutomationRule.code == code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Mã quy tắc '{code}' đã tồn tại")

    rule = AutomationRule(
        code=code,
        name=req.name,
        cluster_id=req.cluster_id,
        description=req.description,
        is_enabled=req.is_enabled,
        config_json=json.dumps(req.config, ensure_ascii=False),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    out = _rule_to_out(rule)
    ws_manager.broadcast_threadsafe("AUTOMATION_RULE_UPDATED", out)
    return out


@router.put(
    "/api/automation/rules/{rule_id}",
    response_model=AutomationRuleOut,
    summary="Cập nhật trạng thái bật/tắt hoặc ngưỡng cấu hình của kịch bản tự động hóa",
)
def update_automation_rule(
    rule_id: int,
    req: AutomationRuleUpdateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_operator),
) -> Any:
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Không tìm thấy quy tắc tự động hóa")

    if req.name is not None:
        rule.name = req.name
    if req.description is not None:
        rule.description = req.description
    if req.is_enabled is not None:
        rule.is_enabled = req.is_enabled
    if req.config is not None:
        merged_cfg = rule.get_config()
        merged_cfg.update(req.config)
        rule.config_json = json.dumps(merged_cfg, ensure_ascii=False)
        _sync_rule_config_to_settings(db, rule)

    db.commit()
    db.refresh(rule)
    out = _rule_to_out(rule)
    ws_manager.broadcast_threadsafe("AUTOMATION_RULE_UPDATED", out)
    return out


@router.delete(
    "/api/automation/rules/{rule_id}",
    summary="Xóa quy tắc tự động hóa tùy chỉnh",
)
def delete_automation_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_operator),
) -> Dict[str, Any]:
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Không tìm thấy quy tắc tự động hóa")
    db.delete(rule)
    db.commit()
    return {"status": "deleted", "rule_id": rule_id}
