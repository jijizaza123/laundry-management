"""ORM 模型：完全映射原有 laundry.db 表结构，新增 order_items 明细表"""
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="staff")  # admin / staff / customer
    name: Mapped[str] = mapped_column(String, nullable=False)
    # 客户账号专用：绑定到 customers 档案。员工账号此列为空
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), unique=True)
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(String, default="")
    member_level: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    items: Mapped[str] = mapped_column(Text, nullable=False, default="")
    original_amount: Mapped[float] = mapped_column(Float, default=0)       # 折前金额
    discount_rate: Mapped[float] = mapped_column(Float, default=1.0)        # 会员折扣率
    member_level_snapshot: Mapped[int] = mapped_column(Integer, default=0)  # 下单时的会员等级
    total_price: Mapped[float] = mapped_column(Float, nullable=False, default=0)  # 折后应收
    deposit: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="received")
    receive_time: Mapped[str] = mapped_column(String, default=now_str)
    expected_pickup: Mapped[str | None] = mapped_column(String)
    actual_pickup: Mapped[str | None] = mapped_column(String)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # 三期新增：订单来源（staff 到店 / online 客户端下单）、关联的上门取件预约、到店复核状态
    source: Mapped[str] = mapped_column(String, default="staff")
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    # confirmed 正常单 / pending 待门店复核 / adjusted 门店已调价待客户确认
    review_status: Mapped[str] = mapped_column(String, default="confirmed")
    # 软删除：删除订单不再物理删行、不再删财务流水（对应 P0-5）
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    customer = relationship("Customer", lazy="joined")
    item_rows = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """订单衣物明细（结构化），原始 orders.items 文本保留用于展示兼容"""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    category: Mapped[str] = mapped_column(String, default="")
    service_name: Mapped[str] = mapped_column(String, default="")
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    subtotal: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[str] = mapped_column(String, default=now_str)

    order = relationship("Order", back_populates="item_rows")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    type: Mapped[str] = mapped_column(String, nullable=False)  # income / expense
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(String, default="")
    transaction_time: Mapped[str] = mapped_column(String, default=now_str)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit: Mapped[str | None] = mapped_column(String, default="件")
    price: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str | None] = mapped_column(String, default="")
    detail: Mapped[str | None] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class ServiceItem(Base):
    __tablename__ = "service_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    unit: Mapped[str | None] = mapped_column(String, default="件")
    category: Mapped[str | None] = mapped_column(String, default="")
    description: Mapped[str | None] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class CareRule(Base):
    """洗护知识库：结构化规则，Agent 只能引用这里的内容，不许自由发挥

    每条规则必须能回答四件事：能不能水洗 / 建议做什么工艺 / 有什么禁忌 / 依据是什么。
    """

    __tablename__ = "care_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fabric: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # 主名称，如 羊绒
    aliases: Mapped[str | None] = mapped_column(String, default="")            # 别名，逗号分隔
    water_wash: Mapped[str] = mapped_column(String, default="")                # 可水洗 / 不可水洗 / 仅手洗
    service: Mapped[str | None] = mapped_column(String, default="")            # 对应价目表服务名
    avoid: Mapped[str | None] = mapped_column(Text, default="")                # 禁忌，分号分隔
    reason: Mapped[str | None] = mapped_column(Text, default="")               # 原因
    source: Mapped[str | None] = mapped_column(String, default="")             # 出处（标准/规范）
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class Appointment(Base):
    """上门取件预约（与洗衣订单拆成两层单）

    预约单只表示"什么时候、去哪里取件"；真正洗什么、多少钱，是到店/取件后生成的订单。
    这样五态订单机不用为"预约"这种非洗涤状态扩容。
    """

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appt_no: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    expected_time: Mapped[str] = mapped_column(String, nullable=False)        # YYYY-MM-DD HH:MM
    address: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, default="")                # 客户备注：几件、什么衣服
    status: Mapped[str] = mapped_column(String, default="pending")            # pending/confirmed/completed/cancelled
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(String, default=now_str)

    customer = relationship("Customer", lazy="joined")


class OrderAmountLog(Base):
    """到店复核的调价流水：门店改一次价就是一条，客户确认后打 confirmed"""

    __tablename__ = "order_amount_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    old_total: Mapped[float] = mapped_column(Float, default=0)
    new_total: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")                      # 为什么改：件数不符/面料需精洗…
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    customer_confirmed: Mapped[int] = mapped_column(Integer, default=0)        # 0 未确认 / 1 已确认
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class ChatMessage(Base):
    """Agent 会话存储：刷新页面后历史还在，也为评估留样本"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String, nullable=False)          # 例：customer:1 / staff:1
    role: Mapped[str] = mapped_column(String, nullable=False)                 # user / assistant
    content: Mapped[str] = mapped_column(Text, default="")
    tools_used: Mapped[str | None] = mapped_column(String, default="")        # 逗号分隔，便于统计
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class Notification(Base):
    """站内消息：调价要客户确认、衣服可取、预约确认 —— 不刷新页面也能看到

    真实项目里这一步是短信/微信模板消息；本地课设用站内消息把链路补完整。
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, default="info")   # price_adjusted / ready / appointment / info
    title: Mapped[str] = mapped_column(String, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    is_read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class AgentMetric(Base):
    """Agent 每轮调用指标：token/耗时/轮次落库，才有"成本与延迟看板"可讲"""

    __tablename__ = "agent_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String, default="")   # customer:1 / staff:1
    side: Mapped[str] = mapped_column(String, default="customer")  # customer / staff
    engine: Mapped[str] = mapped_column(String, default="loop")
    question_chars: Mapped[int] = mapped_column(Integer, default=0)
    question: Mapped[str] = mapped_column(String, default="")       # 截断保存，便于回看坏例子
    answer_chars: Mapped[int] = mapped_column(Integer, default=0)
    rounds: Mapped[int] = mapped_column(Integer, default=0)
    tools_used: Mapped[str] = mapped_column(String, default="")
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String, default=now_str)


class InventoryUsage(Base):
    """耗材用量流水：哪一单、用了什么、用了多少 —— 库存终于和订单挂上钩"""

    __tablename__ = "inventory_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    item_name: Mapped[str] = mapped_column(String, default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    pieces: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String, default=now_str)
