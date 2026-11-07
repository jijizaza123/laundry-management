"""管理端 Agent 路由：员工问答 + 写操作两段式确认 + 调用指标

安全边界：
- 整个路由挂 require_staff，客户端 token 打不进来
- 模型只能提议写操作；真正落库需要员工在前端点确认，回传 action_id
"""
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..agent import run_staff_chat
from ..config import AGENT_ENGINE
from ..db import get_db
from ..deps import get_current_user, require_staff
from ..models import User
from ..schemas import StaffChatRequest
from ..services import chat_service, metric_service

router = APIRouter(prefix="/api/staff", tags=["员工助手"], dependencies=[Depends(require_staff)])


@router.post("/chat", summary="和员工助手对话（写操作需二次确认）")
def staff_chat(
    payload: StaffChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = chat_service.session_key_staff(user.id)
    history = [m.model_dump() for m in payload.history][-12:]
    if not history:
        history = [{"role": h["role"], "content": h["content"]} for h in chat_service.history(db, key)]

    started = time.perf_counter()
    result = run_staff_chat(
        db=db,
        user=user,
        message=payload.message,
        history=history,
        confirm_action_id=payload.confirm_action_id,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    chat_service.append(db, key, "user", payload.message)
    chat_service.append(db, key, "assistant", result["answer"], result["tools_used"])
    metric_service.record(
        db,
        session_key=key,
        side="staff",
        question=payload.message,
        answer=result["answer"],
        rounds=result["rounds"],
        tools_used=result["tools_used"],
        elapsed_ms=elapsed_ms,
        ok=not bool(result.get("error")),
        engine=AGENT_ENGINE,
    )

    return {
        "success": True,
        "data": {
            "answer": result["answer"],
            "tools_used": result["tools_used"],
            "rounds": result["rounds"],
            "elapsed_ms": elapsed_ms,
            "trace": result["trace"],
            "pending_actions": result.get("pending_actions", []),
            "error": bool(result.get("error")),
        },
    }


@router.get("/chat/history", summary="员工助手对话历史")
def staff_chat_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": chat_service.history(db, chat_service.session_key_staff(user.id), limit=30)}


@router.delete("/chat/history", summary="清空员工助手对话历史")
def clear_staff_chat(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat_service.clear(db, chat_service.session_key_staff(user.id))
    return {"success": True, "data": {"cleared": True}}


@router.get("/metrics", summary="Agent 调用指标：调用量、P50/P95 延迟、错误率、轮次")
def agent_metrics(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    return {"success": True, "data": metric_service.summary(db, days=days)}
