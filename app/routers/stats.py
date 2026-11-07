"""统计与财务路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_staff
from ..schemas import TransactionCreate
from ..services import stats_service

router = APIRouter(prefix="/api", tags=["统计"], dependencies=[Depends(require_staff)])


@router.get("/stats", summary="首页看板数据")
def stats(db: Session = Depends(get_db)):
    return stats_service.dashboard(db)


@router.get("/stats/trend", summary="近 N 天订单量与收入趋势")
def trend(days: int = Query(7, ge=1, le=60), db: Session = Depends(get_db)):
    return stats_service.trend(db, days)


@router.get("/stats/daily", summary="日报")
def daily(date: str | None = Query(None, description="日期 YYYY-MM-DD，默认今天"), db: Session = Depends(get_db)):
    return stats_service.daily_report(db, date)


@router.get("/stats/range", summary="区间报表")
def range_report(
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    return stats_service.range_report(db, start_date, end_date)


@router.get("/stats/services", summary="服务项目排行（件数/金额）")
def service_ranking(
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return stats_service.service_ranking(db, start_date, end_date, limit)


@router.get("/transactions", summary="财务流水")
def list_transactions(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    return stats_service.list_transactions(db, limit)


@router.post("/transactions", summary="登记收入/支出")
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    return stats_service.add_transaction(db, payload.type, payload.amount, payload.description)
