"""FastAPI 应用入口"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from .config import STATIC_DIR, TEMPLATE_DIR
from .db import Base, SessionLocal, engine
from .exceptions import ServiceError
from .models import User
from .routers import appointments, auth, catalog, customers, inventory, me, orders, staff_chat, stats
from .security import hash_password
from .services import auth_service

app = FastAPI(title="洗衣店管理系统 API", version="2.1.0", description="课设重构版：分层架构，可直接被 Agent 调用")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# ---------- 统一异常出口：前端依赖 {error, message} 两个字段 ----------
@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "error": exc.message, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    msg = str(first.get("msg", "参数校验失败")).replace("Value error, ", "")
    detail = (field + ": " + msg) if field else msg
    # ctx 里可能带 ValueError 等不可序列化对象，只回传安全字段
    safe_errors = [
        {
            "loc": [str(p) for p in e.get("loc", [])],
            "msg": str(e.get("msg", "")).replace("Value error, ", ""),
            "type": str(e.get("type", "")),
        }
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"success": False, "error": detail, "message": detail, "errors": safe_errors},
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": str(exc.detail), "message": str(exc.detail)},
    )


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)  # 只创建缺失表，不动已有数据
    db = SessionLocal()
    try:
        if not db.execute(select(User)).scalars().first():
            db.add(User(username="admin", password=hash_password("admin123"), role="admin", name="管理员"))
            db.add(User(username="staff", password=hash_password("staff123"), role="staff", name="员工"))
            db.commit()
        auth_service.encrypt_existing_passwords(db)
    finally:
        db.close()


@app.get("/api/health", tags=["系统"], summary="健康检查")
def health():
    return {"status": "ok", "service": "laundry-management", "version": "2.1.0"}


# ---------- 页面 ----------
def _render(request: Request, name: str):
    return templates.TemplateResponse(request, name, {})


@app.get("/", include_in_schema=False)
def index(request: Request):
    return _render(request, "index.html")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    return _render(request, "login.html")


@app.get("/receive", include_in_schema=False)
def receive_page(request: Request):
    return _render(request, "receive.html")


@app.get("/orders", include_in_schema=False)
def orders_page(request: Request):
    return _render(request, "orders.html")


@app.get("/pickup", include_in_schema=False)
def pickup_page(request: Request):
    return _render(request, "pickup.html")


@app.get("/members", include_in_schema=False)
def members_page(request: Request):
    return _render(request, "members.html")


@app.get("/inventory", include_in_schema=False)
def inventory_page(request: Request):
    return _render(request, "inventory.html")


@app.get("/finance", include_in_schema=False)
def finance_page(request: Request):
    return _render(request, "finance.html")


# ---------- 客户端页面（客户账号专用） ----------
@app.get("/me/login", include_in_schema=False)
def me_login_page(request: Request):
    return _render(request, "me_login.html")


@app.get("/me", include_in_schema=False)
def me_page(request: Request):
    return _render(request, "me.html")


@app.get("/me/orders", include_in_schema=False)
def me_orders_page(request: Request):
    return _render(request, "me_orders.html")


@app.get("/me/chat", include_in_schema=False)
def me_chat_page(request: Request):
    return _render(request, "me_chat.html")


@app.get("/chat", include_in_schema=False)
def staff_chat_page(request: Request):
    return _render(request, "chat.html")


@app.get("/me/book", include_in_schema=False)
def me_book_page(request: Request):
    return _render(request, "me_book.html")


@app.get("/me/messages", include_in_schema=False)
def me_messages_page(request: Request):
    return _render(request, "me_messages.html")


# ---------- 管理端三期页面 ----------
@app.get("/review", include_in_schema=False)
def review_page(request: Request):
    return _render(request, "review.html")


@app.get("/appointments", include_in_schema=False)
def appointments_page(request: Request):
    return _render(request, "appointments.html")


@app.get("/metrics", include_in_schema=False)
def metrics_page(request: Request):
    return _render(request, "metrics.html")


# ---------- 静态资源 ----------
app.mount("/css", StaticFiles(directory=STATIC_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=STATIC_DIR / "js"), name="js")

app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(customers.router)
app.include_router(catalog.router)
app.include_router(stats.router)
app.include_router(inventory.router)
app.include_router(me.router)
app.include_router(appointments.router)
app.include_router(staff_chat.router)
