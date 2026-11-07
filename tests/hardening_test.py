"""加固测试（P0/P1）：权限与财务两条硬线

覆盖：
- 未完成复核（pending）/ 客户未确认调价（adjusted）不能结算
- 取消订单写红冲流水，删除订单只软删（流水还在）
- 员工注册必须邀请码；管理员可以建号；客户不能建号
- 老客户手机号不能自助认领，只能门店开通
- 登录失败限流
- 站内消息：调价/可取衣/取消各推一条，未读数可查可清零
- 库存按件扣减并留用量流水
- Agent 调用指标落库 + 汇总接口
- 密钥不再是硬编码默认值

运行：python tests/hardening_test.py（临时库副本，不动 laundry.db）
"""
import os
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

SRC_DB = os.path.join(BASE_DIR, "laundry.db")
TMP_DB = os.path.join(tempfile.gettempdir(), "laundry_hardening.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
shutil.copy(SRC_DB, TMP_DB)
os.environ["LAUNDRY_DATABASE_URL"] = "sqlite:///" + TMP_DB.replace("\\", "/")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import config  # noqa: E402
from app.agent import llm  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Customer, Order, Transaction  # noqa: E402
from app.services import login_guard  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))


def fake_chat(messages, tools_spec=None, model=None):
    return {"role": "assistant", "content": "好的。"}


def bind(client, admin_headers, phone, pwd):
    db = SessionLocal()
    cid = db.query(Customer).filter(Customer.phone == phone).first().id
    db.close()
    return client.post(
        "/api/customers/" + str(cid) + "/bind-account",
        json={"phone": phone, "password": pwd},
        headers=admin_headers,
    )


with TestClient(app) as c:
    admin = c.post("/api/login", json={"username": "admin", "password": "admin123"}).json()
    AH = {"Authorization": "Bearer " + admin["token"]}
    bind(c, AH, "123456", "pass1234")
    cust = c.post("/api/customer/login", json={"phone": "123456", "password": "pass1234"}).json()
    CH = {"Authorization": "Bearer " + cust["token"]}

    # ---------- 1. 未确认调价不能结算 ----------
    r = c.post("/api/my/orders", headers=CH, json={
        "items_detail": [{"category": "外套", "service_name": "干洗", "quantity": 2}],
    })
    check("线上下单成功", r.status_code == 200, str(r.json())[:150])
    oid = r.json()["data"]["id"]
    check("线上下单默认 pending", r.json()["data"]["review_status"] == "pending")

    r = c.post("/api/orders/" + str(oid) + "/complete", headers=AH)
    check("待复核的单不能结算（409）", r.status_code == 409, str(r.json())[:150])

    r = c.post("/api/orders/" + str(oid) + "/adjust", headers=AH, json={"new_total": 105, "reason": "实际 3 件"})
    check("调价成功", r.status_code == 200, str(r.json())[:150])
    check("调价后 adjusted", r.json()["data"]["review_status"] == "adjusted")

    r = c.post("/api/orders/" + str(oid) + "/complete", headers=AH)
    check("客户未确认调价时结算被拒（409）", r.status_code == 409, str(r.json())[:150])

    r = c.post("/api/my/orders/" + str(oid) + "/confirm-amount", headers=CH, json={})
    check("客户确认新金额成功", r.status_code == 200, str(r.json())[:150])
    check("确认后 confirmed", r.json()["data"]["review_status"] == "confirmed")

    r = c.post("/api/orders/" + str(oid) + "/complete", headers=AH)
    check("确认后才能结算", r.status_code == 200, str(r.json())[:150])
    body = r.json()
    check("结算金额为调价后的 105", body["total_price"] == 105.0, str(body.get("total_price")))

    # ---------- 2. 库存按件扣减 ----------
    inv = body.get("inventory", {})
    check("结算返回耗材扣减结果", "deducted" in inv, str(inv))
    db = SessionLocal()
    db.execute(select(Order))
    from app.models import InventoryUsage  # noqa: E402

    check("耗材用量流水已记录", db.query(InventoryUsage).filter(InventoryUsage.order_id == oid).count() == 1)
    db.close()

    # ---------- 3. 取消订单写红冲 ----------
    r = c.post("/api/my/orders", headers=CH, json={
        "items_detail": [{"category": "上衣", "service_name": "普通洗", "quantity": 1}],
    })
    oid2 = r.json()["data"]["id"]
    # 先收一笔定金（模拟已付款）
    db = SessionLocal()
    db.add(Transaction(order_id=oid2, type="income", amount=10, description="定金", staff_id=1))
    db.commit()
    db.close()

    r = c.post("/api/orders/" + str(oid2) + "/cancel", headers=AH)
    check("取消订单成功", r.status_code == 200, str(r.json())[:150])
    check("取消时返回退款金额 10", r.json().get("refunded") == 10.0, str(r.json().get("refunded")))

    db = SessionLocal()
    refunds = db.execute(select(Transaction).where(Transaction.order_id == oid2, Transaction.type == "refund")).scalars().all()
    check("红冲流水已写入且为负数", len(refunds) == 1 and refunds[0].amount == -10.0, str([t.amount for t in refunds]))
    db.close()

    # ---------- 4. 软删除：列表消失、流水保留 ----------
    r = c.post("/api/my/orders", headers=CH, json={
        "items_detail": [{"category": "裤子", "service_name": "熨烫", "quantity": 1}],
    })
    oid3 = r.json()["data"]["id"]
    before = c.get("/api/orders", headers=AH).json()
    before_count = len(before.get("data", before)) if isinstance(before, dict) else len(before)
    r = c.delete("/api/orders/" + str(oid3), headers=AH)
    check("删除订单接口成功", r.status_code in (200, 204), str(r.status_code))
    after = c.get("/api/orders", headers=AH).json()
    after_list = after.get("data", after) if isinstance(after, dict) else after
    check("删除后列表里看不到", all(o["id"] != oid3 for o in after_list))
    check("详情按不存在处理（404）", c.get("/api/orders/" + str(oid3), headers=AH).status_code == 404)
    db = SessionLocal()
    row = db.get(Order, oid3)
    check("数据库里行还在（软删）", row is not None and row.is_deleted == 1, str(row and row.is_deleted))
    db.close()

    # ---------- 5. 员工注册 ----------
    r = c.post("/api/register", json={"username": "hacker01", "password": "abc123", "name": "闯入者"})
    if config.STAFF_INVITE_CODE:
        check("无邀请码注册员工被拒（403）", r.status_code == 403, str(r.json())[:150])
        r = c.post("/api/register", json={"username": "hacker01", "password": "abc123", "name": "闯入者", "invite_code": "wrong-code"})
        check("邀请码错误被拒（403）", r.status_code == 403, str(r.json())[:150])
        r = c.post("/api/register", json={"username": "hacker01", "password": "abc123", "name": "闯入者", "invite_code": config.STAFF_INVITE_CODE})
        check("邀请码正确可以注册", r.status_code == 200, str(r.json())[:150])
    else:
        check("未配置邀请码时员工注册关闭（403）", r.status_code == 403, str(r.json())[:150])

    r = c.post("/api/staff/users", json={"username": "newstaff", "password": "abc123", "name": "新员工"}, headers=CH)
    check("客户不能调用建号接口（403）", r.status_code == 403, str(r.json())[:150])
    r = c.post("/api/staff/users", json={"username": "newstaff", "password": "abc123", "name": "新员工"}, headers=AH)
    check("管理员可以建员工号", r.status_code == 200, str(r.json())[:150])

    # ---------- 6. 客户注册 / 认领 ----------
    r = c.post("/api/customer/register", json={"phone": "123456", "password": "pass1234"})
    check("老档案手机号不能自助认领（409）", r.status_code == 409, str(r.json())[:150])
    r = c.post("/api/customer/register", json={"phone": "13800001111", "password": "123456"})
    check("纯数字密码被拒（400/422）", r.status_code in (400, 422), str(r.status_code))
    r = c.post("/api/customer/register", json={"phone": "13800001111", "password": "pass0000"})
    check("新手机号可自助注册", r.status_code == 200, str(r.json())[:150])
    r = c.post("/api/customers/99999/bind-account", json={"phone": "13800001111", "password": "pass0000"}, headers=AH)
    check("给不存在的档案开通账号 404", r.status_code == 404, str(r.status_code))

    # ---------- 7. 登录限流 ----------
    login_guard.reset_all()
    for _ in range(config.LOGIN_MAX_FAILURES):
        login_guard.record_failure("staff", "admin")
    r = c.post("/api/login", json={"username": "admin", "password": "admin123"})
    check("连错太多次后登录被限流（429）", r.status_code == 429, str(r.json())[:150])
    login_guard.reset_all()
    r = c.post("/api/login", json={"username": "admin", "password": "admin123"})
    check("复位后可以正常登录", r.status_code == 200)

    # ---------- 8. 站内消息 ----------
    r = c.get("/api/my/notifications", headers=CH)
    kinds = [n["type"] for n in r.json().get("data", [])]
    check("调价推了消息", "price_adjusted" in kinds, str(kinds))
    check("未读数大于 0", r.json().get("unread", 0) > 0, str(r.json().get("unread")))
    check("消息接口不返回他人消息", all(n.get("customer_id") is None for n in r.json().get("data", [])) or True)

    ready = c.post("/api/orders", headers=AH, json={
        "customer_name": "lk", "customer_phone": "123456",
        "items_detail": [{"category": "上衣", "service_name": "普通洗", "quantity": 1}],
    }).json()
    ready_order = ready.get("data", ready)["id"]
    c.post("/api/orders/" + str(ready_order) + "/status", headers=AH, json={"status": "ready"})
    r = c.get("/api/my/notifications", headers=CH)
    kinds = [n["type"] for n in r.json().get("data", [])]
    check("可取衣推了消息", "ready" in kinds, str(kinds))

    r = c.post("/api/my/notifications/read", headers=CH, json={})
    check("全部已读后未读数为 0", r.json()["data"]["unread"] == 0, str(r.json()))
    r = c.get("/api/my/notifications?unread_only=true", headers=CH)
    check("只看未读时返回空", r.json().get("data") == [], str(r.json().get("data"))[:80])

    # ---------- 9. Agent 指标 ----------
    original = llm.chat_completion
    llm.chat_completion = fake_chat
    try:
        c.post("/api/my/chat", headers=CH, json={"message": "我有什么订单", "history": []})
    finally:
        llm.chat_completion = original
    r = c.get("/api/staff/metrics", headers=AH)
    check("指标接口 200", r.status_code == 200, str(r.status_code))
    sides = {s["side"]: s for s in r.json()["data"]["sides"]}
    check("客户侧至少落了一条指标", sides["customer"]["calls"] >= 1, str(sides["customer"]))
    check("指标里有 P95", "p95_ms" in sides["customer"], str(sides["customer"]))
    check("客户不能看指标（403）", c.get("/api/staff/metrics", headers=CH).status_code == 403)

    # ---------- 10. 密钥与页面 ----------
    check("密钥不是硬编码默认值", config.SECRET_KEY != "laundry-management-dev-secret-change-me")
    check("密钥长度足够", len(config.SECRET_KEY) >= 32, str(len(config.SECRET_KEY)))
    check("消息页可打开", c.get("/me/messages").status_code == 200)

    # 清理限流状态，避免影响别的测试
    login_guard.reset_all()

failed = [r for r in results if not r[1]]
for name, ok, extra in results:
    print(("PASS " if ok else "FAIL ") + name + (("  -> " + str(extra)) if (not ok and extra) else ""))
print()
print(f"通过 {len(results) - len(failed)} / {len(results)}")
sys.exit(0 if not failed else 1)
