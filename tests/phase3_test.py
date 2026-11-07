"""三期测试：上门取件预约 + 线上点单 + 到店复核 + 会话持久化

运行：python tests/phase3_test.py
临时库副本，不动 laundry.db
"""
import json
import os
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

SRC_DB = os.path.join(BASE_DIR, "laundry.db")
TMP_DB = os.path.join(tempfile.gettempdir(), "laundry_phase3.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
shutil.copy(SRC_DB, TMP_DB)
os.environ["LAUNDRY_DATABASE_URL"] = "sqlite:///" + TMP_DB.replace("\\", "/")

from fastapi.testclient import TestClient  # noqa: E402

from app.agent import llm  # noqa: E402
from app.main import app  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))


def fake_chat(messages, tools_spec=None, model=None):
    return {"role": "assistant", "content": "好的，我查到你的订单了。"}


with TestClient(app) as c:
    # ---------- 账号 ----------
    # P0-3 之后老客户不能自助认领档案，由门店开通（测试里用管理员账号调开通接口）
    r2 = c.post("/api/login", json={"username": "admin", "password": "admin123"})
    S = {"Authorization": "Bearer " + r2.json()["token"]}
    from app.db import SessionLocal  # noqa: E402
    from app.models import Customer  # noqa: E402

    db = SessionLocal()
    for phone, pwd in (("123456", "pass1234"), ("147258", "pass1234")):
        cid = db.query(Customer).filter(Customer.phone == phone).first().id
        c.post("/api/customers/" + str(cid) + "/bind-account", json={"phone": phone, "password": pwd}, headers=S)
    db.close()

    r = c.post("/api/customer/login", json={"phone": "123456", "password": "pass1234"})
    A = {"Authorization": "Bearer " + r.json()["token"]}
    r3 = c.post("/api/customer/login", json={"phone": "147258", "password": "pass1234"})
    B = {"Authorization": "Bearer " + r3.json()["token"]}

    # ---------- 1. 预约校验 ----------
    past = c.post("/api/my/appointments", headers=A,
                  json={"expected_time": "2020-01-01 10:00", "address": "老校区 3 栋"})
    check("过去的预约时间被拒", past.status_code == 400, str(past.json())[:120])
    bad = c.post("/api/my/appointments", headers=A, json={"expected_time": "明天下午", "address": "x"})
    check("时间格式不对被拒", bad.status_code == 400, str(bad.json())[:120])
    empty_addr = c.post("/api/my/appointments", headers=A,
                        json={"expected_time": "2026-12-01 10:00", "address": "   "})
    check("空地址被拒", empty_addr.status_code == 400, str(empty_addr.json())[:120])
    long_time = c.post("/api/my/appointments", headers=A,
                       json={"expected_time": "2027-06-01 10:00", "address": "老校区 3 栋"})
    check("超过 14 天的预约被拒", long_time.status_code == 400, str(long_time.json())[:120])

    from datetime import datetime, timedelta

    when = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 18:00")
    appt = c.post("/api/my/appointments", headers=A, json={"expected_time": when, "address": "老校区 3 栋 402"})
    check("预约创建成功", appt.status_code == 200, str(appt.json())[:120])
    appt_id = appt.json()["data"]["id"]
    check("预约初始状态 pending", appt.json()["data"]["status"] == "pending")
    check("预约号是 A 开头", appt.json()["data"]["appt_no"].startswith("A"))

    mine = c.get("/api/my/appointments", headers=A)
    check("我的预约列表只有自己的", len(mine.json()["data"]) == 1, str(len(mine.json()["data"])))
    b_appt = c.get("/api/my/appointments", headers=B)
    check("B 看不到 A 的预约", len(b_appt.json()["data"]) == 0)

    # 同一客户最多 3 个进行中的预约
    for i in range(2):
        c.post("/api/my/appointments", headers=A,
               json={"expected_time": when, "address": f"老校区 5 栋 {500 + i}"})
    fourth = c.post("/api/my/appointments", headers=A,
                    json={"expected_time": when, "address": "老校区 6 栋 601"})
    check("超过 3 个进行中预约被 409 拦下", fourth.status_code == 409, str(fourth.json())[:120])

    # ---------- 2. 线上点单 ----------
    opts = c.get("/api/my/options", headers=A)
    check("选项接口返回分类/服务/面料", opts.status_code == 200 and len(opts.json()["data"]["services"]) == 5)
    check("选项接口不带手机号参数", "phone" not in json.dumps(opts.json(), ensure_ascii=False))

    items = [{"category": "外套", "service_name": "干洗", "quantity": 2}]
    quote = c.post("/api/my/quote", headers=A, json={"items_detail": items})
    check("试算成功", quote.status_code == 200, str(quote.json())[:120])
    quoted_total = quote.json()["data"]["total"]

    order = c.post("/api/my/orders", headers=A,
                   json={"items_detail": items, "appointment_id": appt_id,
                         "expected_pickup": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d 18:00")})
    check("线上下单成功", order.status_code == 200, str(order.json())[:150])
    od = order.json()["data"]
    check("金额等于服务端试算", abs(od["total_price"] - quoted_total) < 0.01, f"{od['total_price']} vs {quoted_total}")
    check("订单标记为线上来源", od["source"] == "online")
    check("订单待复核", od["review_status"] == "pending", od["review_status"])
    check("订单关联了预约", od["appointment_id"] == appt_id, str(od["appointment_id"]))
    order_id = od["id"]
    order_no = od["order_no"]

    # 客户试图自己塞总价：字段被忽略，金额仍是服务端算的
    fake = c.post("/api/my/orders", headers=A,
                  json={"items_detail": items, "declared_total": 1})
    check("客户端塞总价无用，金额仍按服务端算",
          fake.status_code == 200 and abs(fake.json()["data"]["total_price"] - quoted_total) < 0.01,
          str(fake.json())[:160])
    fake_id = fake.json()["data"]["id"]

    # 下单时试图关联别人的预约
    other_appt = c.post("/api/my/appointments", headers=B,
                        json={"expected_time": when, "address": "B 家"})
    other_id = other_appt.json()["data"]["id"]
    cross = c.post("/api/my/orders", headers=A, json={"items_detail": items, "appointment_id": other_id})
    check("不能关联他人预约", cross.status_code == 404, str(cross.json())[:120])

    # ---------- 3. 到店复核 ----------
    pending = c.get("/api/orders/review-pending", headers=S)
    check("门店能看到待复核单", any(o["id"] == order_id for o in pending.json()["orders"]))
    check("客户看不到复核列表（403）", c.get("/api/orders/review-pending", headers=A).status_code == 403)

    no_reason = c.post(f"/api/orders/{order_id}/adjust", headers=S, json={"new_total": 80, "reason": ""})
    check("调价不写原因被拒", no_reason.status_code == 400, str(no_reason.json())[:120])
    same = c.post(f"/api/orders/{order_id}/adjust", headers=S,
                  json={"new_total": quoted_total, "reason": "件数一致"})
    check("金额没变化不算调价", same.status_code == 400)
    negative = c.post(f"/api/orders/{order_id}/adjust", headers=S, json={"new_total": 0, "reason": "x"})
    check("新金额必须大于 0", negative.status_code == 400)

    new_total = round(quoted_total + 35, 2)
    adjusted = c.post(f"/api/orders/{order_id}/adjust", headers=S,
                      json={"new_total": new_total, "reason": "实际 3 件，客户下单填了 2 件"})
    check("调价成功", adjusted.status_code == 200, str(adjusted.json())[:120])
    check("调价后进入待客户确认", adjusted.json()["data"]["review_status"] == "adjusted")

    mine_detail = c.get(f"/api/my/orders/{order_id}", headers=A)
    logs = mine_detail.json()["data"]["amount_logs"]
    check("客户能看到调价记录", len(logs) == 1 and abs(logs[0]["new_total"] - new_total) < 0.01, str(logs)[:160])
    check("调价原因传达到客户", "3 件" in logs[0]["reason"])

    confirm = c.post(f"/api/my/orders/{order_id}/confirm-amount", headers=A, json={})
    check("客户确认金额成功", confirm.status_code == 200, str(confirm.json())[:120])
    check("确认后状态回到 confirmed", confirm.json()["data"]["review_status"] == "confirmed")
    after = c.get(f"/api/my/orders/{order_id}", headers=A).json()["data"]
    check("确认后调价记录清空", len(after["amount_logs"]) == 0)
    check("确认后应收变成新金额", abs(after["total_price"] - new_total) < 0.01, str(after["total_price"]))
    check("折前金额保留客户下单时快照", abs(after["original_amount"] - quoted_total) < 0.01, str(after["original_amount"]))

    twice = c.post(f"/api/my/orders/{order_id}/confirm-amount", headers=A, json={})
    check("重复确认被 409 拦下", twice.status_code == 409, str(twice.json())[:120])
    cross_confirm = c.post(f"/api/my/orders/{order_id}/confirm-amount", headers=B, json={})
    check("别人的单确认不了（404）", cross_confirm.status_code == 404)

    # 第二个单：复核通过（金额不变）
    order2 = c.post("/api/my/orders", headers=A, json={"items_detail": items})
    oid2 = order2.json()["data"]["id"]
    approve = c.post(f"/api/orders/{oid2}/approve", headers=S, json={})
    check("复核通过成功", approve.status_code == 200, str(approve.json())[:120])
    check("通过后不再需要客户确认", approve.json()["data"]["review_status"] == "confirmed")
    again = c.post(f"/api/orders/{oid2}/approve", headers=S, json={})
    check("重复通过被 409", again.status_code == 409)

    # ---------- 4. 预约状态推进 ----------
    listed = c.get("/api/appointments", headers=S)
    check("门店能看到预约列表", len(listed.json()["data"]) >= 3)
    check("客户看不到门店预约列表（403）", c.get("/api/appointments", headers=A).status_code == 403)
    ok = c.patch(f"/api/appointments/{appt_id}", headers=S, json={"status": "confirmed"})
    check("确认预约成功", ok.status_code == 200, str(ok.json())[:120])
    illegal = c.patch(f"/api/appointments/{appt_id}", headers=S, json={"status": "pending"})
    check("已确认不能退回待确认", illegal.status_code == 409, str(illegal.json())[:120])
    done = c.patch(f"/api/appointments/{appt_id}", headers=S, json={"status": "completed"})
    check("标记已取件成功", done.status_code == 200)
    check("预约完成后客户侧同步", any(a["status"] == "completed" for a in c.get("/api/my/appointments", headers=A).json()["data"]))

    # ---------- 5. 会话持久化 ----------
    original = llm.chat_completion
    llm.chat_completion = fake_chat
    try:
        first = c.post("/api/my/chat", headers=A, json={"message": "我有几件能取了？", "history": []})
        second = c.post("/api/my/chat", headers=A, json={"message": "那我还欠多少钱", "history": []})
    finally:
        llm.chat_completion = original
    check("第一轮对话成功", first.status_code == 200)
    check("第二轮对话成功", second.status_code == 200)

    hist = c.get("/api/my/chat/history", headers=A)
    entries = hist.json()["data"]
    check("历史里有两轮四条消息", len(entries) == 4, str(len(entries)))
    check("历史顺序是 user→assistant", entries[0]["role"] == "user" and entries[1]["role"] == "assistant", str(entries)[:120])
    check("B 看不到 A 的对话", len(c.get("/api/my/chat/history", headers=B).json()["data"]) == 0)

    cleared = c.request("DELETE", "/api/my/chat/history", headers=A)
    check("清空历史成功", cleared.status_code == 200)
    check("清空后为空", len(c.get("/api/my/chat/history", headers=A).json()["data"]) == 0)

    # ---------- 6. 页面与静态资源 ----------
    for path in ("/me/book", "/review", "/appointments"):
        check(f"页面 {path} 可访问", c.get(path).status_code == 200)
    for path in ("/js/me_book.js", "/js/review.js", "/js/appointments.js"):
        check(f"资源 {path} 可访问", c.get(path).status_code == 200)

    # ---------- 7. 主数据没有被测试写坏 ----------
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Order

    db = SessionLocal()
    try:
        total = len(db.execute(select(Order)).scalars().all())
        check("临时库订单数 = 原 11 + 测试新增 3", total == 14, str(total))
    finally:
        db.close()

passed = sum(1 for _, ok, _ in results if ok)
print("=" * 60)
for name, ok, extra in results:
    print(("PASS " if ok else "FAIL ") + name + (("  <- " + extra) if (extra and not ok) else ""))
print("=" * 60)
print(f"通过 {passed} / {len(results)}")
sys.exit(0 if passed == len(results) else 1)
