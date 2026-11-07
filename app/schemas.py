"""Pydantic v2 数据契约（同时用于 HTTP 校验与 Agent 工具参数生成 JSON Schema）"""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., description="登录用户名", min_length=1, max_length=50)
    password: str = Field(..., description="登录密码", min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(..., description="用户名", min_length=2, max_length=50)
    password: str = Field(..., description="密码", min_length=3, max_length=128)
    name: str = Field(..., description="真实姓名", min_length=1, max_length=50)
    invite_code: str | None = Field(None, description="员工邀请码；没配邀请码时公开注册是关闭的")


class BindAccountRequest(BaseModel):
    """门店帮老客户开通客户端账号：历史档案已经存在，不能让他自己认领"""

    phone: str = Field(..., description="客户手机号（与档案一致）", min_length=4, max_length=20)
    password: str = Field(..., description="初始密码，至少 6 位", min_length=6, max_length=128)
    name: str | None = Field(None, description="账号显示名，选填")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    name: str


class LoginResponse(BaseModel):
    success: bool = True
    token: str
    user: UserOut


class CustomerLoginRequest(BaseModel):
    phone: str = Field(..., description="注册手机号", min_length=4, max_length=20)
    password: str = Field(..., description="登录密码", min_length=1, max_length=128)

    @field_validator("phone")
    @classmethod
    def _strip_phone(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("手机号不能为空")
        return v


class CustomerRegisterRequest(BaseModel):
    phone: str = Field(..., description="手机号，注册后作为登录账号", min_length=4, max_length=20)
    password: str = Field(..., description="密码，至少 4 位", min_length=4, max_length=128)
    name: str | None = Field(None, description="姓名，选填；已有档案时以档案为准")

    @field_validator("phone")
    @classmethod
    def _strip_phone(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("手机号不能为空")
        return v


class ChatMessage(BaseModel):
    role: str = Field(..., description="user 或 assistant")
    content: str = Field(..., description="消息内容")

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        if v not in ("user", "assistant"):
            raise ValueError("role 只能是 user 或 assistant")
        return v


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户这一句提问", min_length=1, max_length=800)
    history: list[ChatMessage] = Field(default_factory=list, description="最近几轮对话，用于指代消解")


class AppointmentCreateRequest(BaseModel):
    expected_time: str = Field(..., description="上门时间，格式 2026-11-08 18:00", max_length=32)
    address: str = Field(..., description="取件地址", max_length=200)
    note: str | None = Field(None, description="备注：大概几件、什么衣服", max_length=300)


class AmountAdjustRequest(BaseModel):
    new_total: float = Field(..., description="复核后的应收金额")
    reason: str = Field(..., description="调价原因，必填", max_length=300)


class AppointmentStatusRequest(BaseModel):
    status: str = Field(..., description="confirmed / completed / cancelled")


class StaffChatRequest(BaseModel):
    """管理端 Agent：带上会话 id，便于确认写操作时找回上下文"""

    message: str = Field(..., min_length=1, max_length=800)
    history: list[ChatMessage] = Field(default_factory=list)
    confirm_action_id: str | None = Field(None, description="用户确认后回传的待执行动作 id")


class CustomerCreate(BaseModel):
    name: str = Field(..., description="客户姓名")
    phone: str = Field(..., description="手机号，作为客户唯一标识")
    address: str = Field("", description="客户地址")
    member_level: int = Field(0, ge=0, le=4, description="会员等级 0普通客户 1普通会员 2银卡 3金卡 4钻石")

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("手机号不能为空")
        return v


class CustomerUpdate(BaseModel):
    name: str | None = Field(None, description="客户姓名")
    phone: str | None = Field(None, description="手机号")
    address: str | None = Field(None, description="客户地址")
    member_level: int | None = Field(None, ge=0, le=4, description="会员等级")
    points: int | None = Field(None, ge=0, description="积分")


class OrderItemIn(BaseModel):
    category: str = Field("未分类", description="衣物分类，如：上衣 / 外套")
    service_name: str = Field(..., description="服务项目名称，必须是服务价目表里已有的项目，如：干洗")
    quantity: int = Field(1, ge=1, description="件数")


class QuoteRequest(BaseModel):
    items_detail: list[OrderItemIn] | None = Field(None, description="结构化衣物明细，推荐使用")
    items: str | None = Field(None, description="兼容用：明细文本，每行 分类 - 服务 (¥单价/件) x数量")
    customer_phone: str | None = Field(None, description="客户手机号，用于套用会员折扣")


class OnlineOrderRequest(BaseModel):
    """客户端下单：没有客户手机号字段，也没有 total_price 字段（价格只能由服务端算）"""

    items_detail: list[OrderItemIn] | None = Field(None, description="结构化明细")
    items: str | None = Field(None, description="旧文本明细，兼容用；两者至少给一个")
    expected_pickup: str | None = Field(None, description="期望取衣时间", max_length=32)
    appointment_id: int | None = Field(None, description="关联的上门取件预约 id")


class OrderCreate(BaseModel):
    customer_name: str = Field(..., description="客户姓名")
    customer_phone: str = Field(..., description="客户手机号")
    items_detail: list[OrderItemIn] | None = Field(None, description="结构化衣物明细，推荐使用")
    items: str | None = Field(None, description="兼容用：明细文本")
    total_price: float | None = Field(None, description="仅用于校验：与后端计算结果不一致会被拒绝")
    deposit: float = Field(0, ge=0, description="预收定金（元）")
    pay_now: bool = Field(False, description="是否在收衣时立即收取定金")
    expected_pickup: str | None = Field(None, description="预计取衣时间，格式 YYYY-MM-DD HH:MM:SS")

    @field_validator("items")
    @classmethod
    def _check_items(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("衣物明细不能为空")
        return v


class OrderUpdate(BaseModel):
    items_detail: list[OrderItemIn] | None = Field(None, description="结构化衣物明细")
    items: str | None = Field(None, description="兼容用：明细文本")
    total_price: float | None = Field(None, description="仅用于校验")
    deposit: float | None = Field(None, ge=0, description="定金")


class OrderStatusRequest(BaseModel):
    status: str = Field(..., description="目标状态：washing 洗涤中 / ready 可取衣 / completed 已完成 / cancelled 已取消")


class ServiceItemCreate(BaseModel):
    name: str = Field(..., description="服务项目名称，如：干洗")
    price: float = Field(..., ge=0, description="单价（元）")
    unit: str = Field("件", description="计价单位")
    category: str = Field("", description="服务分类，如水洗/干洗/熨烫")
    description: str = Field("", description="服务说明")


class CategoryCreate(BaseModel):
    name: str = Field(..., description="衣物分类名称，如：上衣")
    description: str = Field("", description="分类说明")


class InventoryCreate(BaseModel):
    name: str = Field(..., description="耗材名称，如：洗衣液")
    quantity: int = Field(0, ge=0, description="库存数量")
    unit: str = Field("件", description="单位")
    price: float = Field(0, ge=0, description="单价")


class TransactionCreate(BaseModel):
    type: str = Field(..., description="类型：income 收入 / expense 支出")
    amount: float = Field(..., gt=0, description="金额（元）")
    description: str = Field("", description="备注")

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in ("income", "expense"):
            raise ValueError("type 只能是 income 或 expense")
        return v
