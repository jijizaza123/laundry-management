"""四期测试：管理端 Agent（工具白名单 + 写操作两段式确认 + 权限边界）

运行：python tests/staff_agent_test.py
"""
import json
import os
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

TMP_DB = os.path.join(tempfile.gettempdir(), "laundry_staff_agent.db")
for suffix in ("", "-wal", "-shm"):
    path = TMP_DB + suffix
    if os.path.exists(path):
        os.remove(path)
shutil.copy(os.path.join(BASE_DIR, "laundry.db"), TMP_DB)
os.environ["LAUNDRY_DATABASE_URL"] = "sqlite:///" + TMP_DB.replace("\\", "/")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agent import llm, staff_graph  # noqa: E402
from app.agent.staff_graph import _Ctx  # noqa: E402
from app.agent.staff_tools import ACTION_STORE, execute_action, run_staff_tool  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Order, User  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# 用现成的订单做写操作验证
db = SessionLocal()
order = db.execute(select(Order).where(Order.status == "received")).scalars().first()
order_no = order.order_no
order_id = order.id
admin = db.execute(select(User).where(User.username == "admin")).scalars().first()
staff = db.execute(select(User).where(User.username == "staff")).scalars().first()
ctx_admin = _Ctx(db, admin)
ctx_staff = _Ctx(db, staff)

# ---------- 1. 工具层 ----------
r = run_staff_tool(ctx_admin, "query_orders", {"limit": 3})
check("工具有订单列表", r["ok"] and r["data"]["count"] >= 1, str(r)[:140])
check("列表只给摘要（不含完整明细表）", "items_detail" not in json.dumps(r, ensure_ascii=False))
r = run_staff_tool(ctx_admin, "query_order_detail", {"order_no": order_no})
check("按单号查详情", r["ok"] and r["data"]["order_no"] == order_no, str(r)[:140])
check("查不存在订单给出可读原因", run_staff_tool(ctx_admin, "query_order_detail", {"order_no": "999"})["ok"] is False)
check("今日概览可用", run_staff_tool(ctx_admin, "query_today_overview", {})["ok"] is True)
check("待复核列表可用", run_staff_tool(ctx_admin, "query_review_pending", {})["ok"] is True)
check("按手机号查客户可用", run_staff_tool(ctx_admin, "query_customer", {"phone": "147258"})["ok"] is True)
check("查不到客户时给原因", run_staff_tool(ctx_admin, "query_customer", {"phone": "000000"})["ok"] is False)
check("洗护规则命中", run_staff_tool(ctx_admin, "query_care_rule", {"fabric": "羊绒"})["found"] is True)
check("洗护规则未命中不瞎编",
      run_staff_tool(ctx_admin, "query_care_rule", {"fabric": "塑料"})["found"] is False)
check("价目表可用", len(run_staff_tool(ctx_admin, "query_price_list", {})["data"]["services"]) == 5)
check("未知工具直接拒绝", run_staff_tool(ctx_admin, "drop_database", {})["ok"] is False)
check("参数类型错误给可读提示", "参数不正确" in run_staff_tool(ctx_admin, "query_customer", {"phone": 1, "x": 2})["error"]
      or run_staff_tool(ctx_admin, "query_customer", {"x": 2})["ok"] is False)

# ---------- 2. 写操作两段式 ----------
before_status = db.get(Order, order_id).status
proposed = run_staff_tool(ctx_admin, "propose_change_status", {"order_no": order_no, "status": "ready"})
check("提议改状态返回动作卡", proposed["ok"] and proposed["data"]["require_confirm"] is True, str(proposed)[:160])
action_id = proposed["data"]["action_id"]
db.expire_all()
check("提议阶段没有真的改库", db.get(Order, order_id).status == before_status, db.get(Order, order_id).status)

bad = execute_action(db, staff, action_id)
check("别的账号确认不了这个动作", bad["ok"] is False, str(bad)[:120])

done = execute_action(db, admin, action_id)
check("本人确认后执行成功", done["ok"] is True, str(done)[:140])
db.expire_all()
check("确认后状态真的变了", db.get(Order, order_id).status == "ready", db.get(Order, order_id).status)
check("同一个 action_id 不能重复执行", execute_action(db, admin, action_id)["ok"] is False)
check("过期/不存在的 action_id 给可读原因", execute_action(db, admin, "act_not_exist")["ok"] is False)
check("动作执行完即从暂存里移除", action_id not in ACTION_STORE)

illegal = run_staff_tool(ctx_admin, "propose_change_status", {"order_no": order_no, "status": "flying"})
check("非法状态不生成动作卡", illegal["ok"] is False, str(illegal)[:120])

# ---------- 3. 图循环（模型打桩） ----------
def fake_chat(messages, tools_spec=None, model=None):
    # 第一轮：调工具；之后：出答案
    last = messages[-1]
    if last.get("role") == "user":
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "query_orders", "arguments": json.dumps({"limit": 2})}},
        ]}
    return {"role": "assistant", "content": "最近 2 单我给你列出来了，其余可以到订单页筛。"}


original = llm.chat_completion
llm.chat_completion = fake_chat
try:
    res = staff_graph.run_staff_chat(db, admin, "今天有什么单", history=[])
finally:
    llm.chat_completion = original
check("图跑完一轮工具后出答案", res["rounds"] == 2 and "最近 2 单" in res["answer"], str(res)[:160])
check("trace 里记录了工具调用", any(t.get("node") == "tool" for t in res["trace"]))


def fake_propose(messages, tools_spec=None, model=None):
    if messages[-1].get("role") == "user":
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "propose_change_status",
                          "arguments": json.dumps({"order_no": order_no, "status": "washing"})}},
        ]}
    return {"role": "assistant", "content": "动作卡给你了，确认才执行。"}


original = llm.chat_completion
llm.chat_completion = fake_propose
try:
    res2 = staff_graph.run_staff_chat(db, admin, "把这一单改成洗涤中", history=[])
finally:
    llm.chat_completion = original
check("写操作会带出 pending_actions 给前端", len(res2["pending_actions"]) == 1, str(res2["pending_actions"]))
check("pending_actions 带 action_id 与摘要",
      res2["pending_actions"][0]["action_id"].startswith("act_")
      and "改成「洗涤中」" in res2["pending_actions"][0]["summary"], str(res2["pending_actions"]))
db.expire_all()
check("模型提议阶段库里仍未变", db.get(Order, order_id).status == "ready")

# ---------- 4. HTTP 层 ----------
with TestClient(app) as c:
    admin_tok = c.post("/api/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    staff_tok = c.post("/api/login", json={"username": "staff", "password": "staff123"}).json()["token"]
    S_admin = {"Authorization": "Bearer " + admin_tok}
    S_staff = {"Authorization": "Bearer " + staff_tok}

    # 新客户自助注册就能登录（P0-3 之后老档案只能门店开通，这里用一个全新号）
    c.post("/api/customer/register", json={"phone": "13911112222", "password": "pass1234", "name": "访客"})
    cust = c.post("/api/customer/login", json={"phone": "13911112222", "password": "pass1234"}).json()
    C = {"Authorization": "Bearer " + cust["token"]}

    check("客户打不进员工助手（403）",
          c.post("/api/staff/chat", headers=C, json={"message": "查所有订单"}).status_code == 403)
    check("客户看不到员工对话历史（403）", c.get("/api/staff/chat/history", headers=C).status_code == 403)

    llm.chat_completion = fake_chat
    try:
        ok = c.post("/api/staff/chat", headers=S_admin, json={"message": "今天有什么单", "history": []})
    finally:
        llm.chat_completion = original
    check("员工可以正常对话", ok.status_code == 200, str(ok.json())[:140])

    h1 = c.get("/api/staff/chat/history", headers=S_admin).json()["data"]
    check("员工对话落库", len(h1) >= 2, str(len(h1)))
    h2 = c.get("/api/staff/chat/history", headers=S_staff).json()["data"]
    check("另一个员工看不到别人的对话", len(h2) == 0, str(len(h2)))

    # 确认动作走 HTTP
    card = c.post("/api/staff/chat", headers=S_admin, json={"message": "x", "history": []},
                  ).json()  # 这次用假模型，不产生动作，只验证接口形状
    check("接口返回结构完整", card["success"] is True and "pending_actions" in card["data"])

    cleared = c.request("DELETE", "/api/staff/chat/history", headers=S_admin)
    check("清空员工历史成功", cleared.status_code == 200)
    check("清空后为空", len(c.get("/api/staff/chat/history", headers=S_admin).json()["data"]) == 0)

    check("页面 /chat 可访问", c.get("/chat").status_code == 200)
    check("资源 /js/chat.js 可访问", c.get("/js/chat.js").status_code == 200)

db.close()

passed = sum(1 for _, ok, _ in results if ok)
print("=" * 60)
for name, ok, extra in results:
    print(("PASS " if ok else "FAIL ") + name + (("  <- " + extra) if (extra and not ok) else ""))
print("=" * 60)
print(f"通过 {passed} / {len(results)}")
sys.exit(0 if passed == len(results) else 1)
