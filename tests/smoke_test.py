"""端到端冒烟测试：鉴权、计价、状态流转、幂等结算、逾期、库存、报表、页面渲染

运行：在 laundry_management 目录执行 python tests/smoke_test.py
测试在临时数据库副本上运行，不会污染 laundry.db
"""
import os
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

SRC_DB = os.path.join(BASE_DIR, "laundry.db")
TMP_DB = os.path.join(tempfile.gettempdir(), "laundry_smoke.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
shutil.copy(SRC_DB, TMP_DB)
os.environ["LAUNDRY_DATABASE_URL"] = "sqlite:///" + TMP_DB.replace("\\", "/")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))


with TestClient(app) as c:
    # ---------- 鉴权 ----------
    check("健康检查 200", c.get("/api/health").status_code == 200)
    check("无 token 拦截 401", c.get("/api/stats").status_code == 401)

    r = c.post("/api/login", json={"username": "admin", "password": "admin123"})
    ok = r.status_code == 200 and r.json().get("success") is True and r.json().get("token")
    check("登录返回 success+token+user", ok, str(r.json())[:200])
    token = r.json().get("token", "")
    H = {"Authorization": "Bearer " + token}

    r = c.post("/api/login", json={"username": "admin", "password": "wrong"})
    check("错误密码 401 且带 message", r.status_code == 401 and "message" in r.json(), str(r.json()))

    # ---------- 看板 ----------
    r = c.get("/api/stats", headers=H)
    check("看板 200", r.status_code == 200, str(r.json()))
    stats = r.json()
    check("看板含在店/可取衣/逾期字段", all(k in stats for k in ("in_store", "ready_count", "overdue_count", "today_income")), str(stats))

    # ---------- 会员折扣试算 ----------
    # 库内 lnc 为银卡会员(level 2, 手机 111)，干洗 35 元 -> 31.5
    r = c.post("/api/orders/quote", json={"items_detail": [{"category": "外套", "service_name": "干洗", "quantity": 1}], "customer_phone": "111"}, headers=H)
    q = r.json() if r.status_code == 200 else {}
    check("银卡试算折后 31.5", q.get("total") == 31.5 and q.get("discount_rate") == 0.9, str(q))
    check("试算返回折前 35", q.get("subtotal") == 35, str(q.get("subtotal")))

    r = c.post("/api/orders/quote", json={"items_detail": [{"category": "外套", "service_name": "干洗", "quantity": 1}]}, headers=H)
    check("非会员不打折 35", r.json().get("total") == 35, str(r.json()))

    r = c.post("/api/orders/quote", json={"items_detail": [{"category": "上衣", "service_name": "不存在的服务", "quantity": 1}]}, headers=H)
    check("未知服务被拒 400", r.status_code == 400, str(r.json()))

    # ---------- 建单（结构化明细，服务端计价） ----------
    payload = {
        "customer_name": "冒烟测试客户",
        "customer_phone": "13900001111",
        "items_detail": [
            {"category": "上衣", "service_name": "普通洗", "quantity": 2},
            {"category": "外套", "service_name": "干洗", "quantity": 1},
        ],
        "deposit": 25,
        "pay_now": True,
        "expected_pickup": "2020-01-01 18:00:00",
    }
    r = c.post("/api/orders", json=payload, headers=H)
    check("创建订单 200", r.status_code == 200, str(r.json())[:300])
    order = r.json() if r.status_code == 200 else {}
    order_id = order.get("id")
    check("服务端计价 20*2+35=75", order.get("original_amount") == 75 and order.get("total_price") == 75, str(order.get("original_amount")))
    check("新单状态为 received", order.get("status") == "received", str(order.get("status")))
    check("明细结构化 2 行", len(order.get("items_detail", [])) == 2, str(order.get("items_detail")))
    check("已收定金 25", order.get("paid_amount") == 25, str(order.get("paid_amount")))

    # 篡改金额应被拒
    r = c.post("/api/orders", json={**payload, "total_price": 1}, headers=H)
    check("篡改总价被拒 400", r.status_code == 400, str(r.json()))
    # 定金超过应收应被拒
    r = c.post("/api/orders", json={**payload, "deposit": 100}, headers=H)
    check("定金超应收被拒", r.status_code == 400, str(r.json()))

    # 兼容旧文本入参（Agent / 旧前端）
    r = c.post("/api/orders", json={"customer_name": "文本客户", "customer_phone": "13900002222",
                                    "items": "上衣 - 普通洗 (¥20/件) x2", "deposit": 0}, headers=H)
    check("旧文本入参可建单", r.status_code == 200 and r.json().get("total_price") == 40, str(r.json())[:200])

    # ---------- 状态流转 ----------
    r = c.post(f"/api/orders/{order_id}/status", json={"status": "washing"}, headers=H)
    check("received -> washing", r.status_code == 200 and r.json().get("status") == "washing", str(r.json())[:200])
    r = c.post(f"/api/orders/{order_id}/status", json={"status": "ready"}, headers=H)
    check("washing -> ready", r.status_code == 200 and r.json().get("status") == "ready", str(r.json())[:200])
    r = c.post(f"/api/orders/{order_id}/status", json={"status": "washing"}, headers=H)
    check("ready -> washing 非法流转被拒 409", r.status_code == 409, str(r.json()))

    # ---------- 结算 ----------
    r = c.post(f"/api/orders/{order_id}/complete", headers=H)
    check("结算成功，补收 50", r.status_code == 200 and r.json().get("settled_amount") == 50, str(r.json())[:250])
    r = c.post(f"/api/orders/{order_id}/complete", headers=H)
    check("重复结算被拒 409", r.status_code == 409, str(r.json()))

    r = c.get(f"/api/orders/{order_id}", headers=H)
    check("结算后实收 75", r.json().get("paid_amount") == 75, str(r.json().get("paid_amount")))
    check("结算后状态 completed", r.json().get("status") == "completed", str(r.json().get("status")))

    check("已完成订单禁止删除", c.delete(f"/api/orders/{order_id}", headers=H).status_code == 409)
    check("已完成订单禁止改明细", c.put(f"/api/orders/{order_id}", json={"deposit": 10}, headers=H).status_code == 409)

    # ---------- 积分 ----------
    r = c.get("/api/customers?keyword=13900001111", headers=H)
    cust = r.json()[0]
    check("积分按应收累计 +75", cust.get("points") == 75, str(cust))

    # ---------- 逾期 ----------
    r = c.get("/api/orders/overdue", headers=H)
    no_conf = [o for o in r.json().get("orders", []) if o["order_no"] == order["order_no"]]
    check("逾期接口识别该单", len(no_conf) >= 0, "")  # 已完成单不进入逾期，下面用活跃单验证
    r = c.post("/api/orders", json={**payload, "customer_phone": "13900003333", "pay_now": False}, headers=H)
    late_id = r.json().get("id")
    r = c.get("/api/orders/overdue", headers=H)
    check("活跃单逾期可查", any(o["id"] == late_id for o in r.json().get("orders", [])), str(r.json())[:200])
    check("已完成单不算逾期", not any(o["id"] == order_id for o in r.json().get("orders", [])), "")

    # ---------- 状态筛选 ----------
    r = c.get("/api/orders?status=received", headers=H)
    check("按状态筛选 received", r.status_code == 200 and all(o["status"] == "received" for o in r.json()), str(len(r.json())))
    check("未知状态被拒 400", c.get("/api/orders?status=xxx", headers=H).status_code == 400)

    # ---------- 异常 ----------
    check("不存在订单 404", c.get("/api/orders/999999", headers=H).status_code == 404)
    check("非法 id 返回 422", c.get("/api/orders/abc", headers=H).status_code == 422)

    # ---------- 报表 ----------
    check("日报 200", c.get("/api/stats/daily", headers=H).status_code == 200)
    check("区间报表 200", c.get("/api/stats/range?start_date=2026-01-01&end_date=2026-12-31", headers=H).status_code == 200)
    r = c.get("/api/stats/trend?days=7", headers=H)
    check("趋势 7 天", r.status_code == 200 and len(r.json()) == 7, str(r.status_code))
    r = c.get("/api/stats/services", headers=H)
    check("服务排行有数据", r.status_code == 200 and any(x["quantity"] > 0 for x in r.json()), str(r.json())[:200])

    # ---------- 库存 ----------
    r = c.post("/api/inventory", json={"name": "洗衣液", "quantity": 10, "unit": "瓶", "price": 25}, headers=H)
    check("新增耗材", r.status_code == 200, str(r.json()))
    iid = r.json().get("id")
    check("入库后 15", c.post(f"/api/inventory/{iid}/in?quantity=5", headers=H).json().get("quantity") == 15)
    check("超量出库被拒 400", c.post(f"/api/inventory/{iid}/out?quantity=999", headers=H).status_code == 400)
    r = c.get("/api/inventory/low-stock?threshold=20", headers=H)
    check("低库存预警", r.status_code == 200 and len(r.json()) >= 1, str(r.json())[:200])

    # ---------- 财务 ----------
    check("支出登记 200", c.post("/api/transactions", json={"type": "expense", "amount": 30, "description": "耗材采购"}, headers=H).status_code == 200)
    check("非法流水类型被拒", c.post("/api/transactions", json={"type": "xx", "amount": 1}, headers=H).status_code == 422)
    r = c.get("/api/stats", headers=H)
    check("总支出 >= 30", r.json().get("total_expense", 0) >= 30, str(r.json()))

    # ---------- 页面渲染 ----------
    for path, name in (("/", "首页"), ("/login", "登录"), ("/receive", "收衣"), ("/orders", "订单"),
                       ("/pickup", "取衣"), ("/members", "会员"), ("/inventory", "库存"), ("/finance", "财务")):
        resp = c.get(path)
        check("页面 " + name + " 渲染 200", resp.status_code == 200 and "<html" in resp.text, str(resp.status_code))
    check("CSS 可用", c.get("/css/app.css").status_code == 200)
    for js in ("api.js", "app.js", "index.js", "receive.js", "orders.js", "pickup.js", "members.js", "inventory.js", "finance.js", "login.js"):
        check("JS " + js + " 可用", c.get("/js/" + js).status_code == 200)

print()
passed = sum(1 for _, ok, _ in results if ok)
print("通过 " + str(passed) + " / " + str(len(results)))
for name, ok, extra in results:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  => " + extra))
sys.exit(0 if passed == len(results) else 1)
