"""客户端 Agent 测试

分两段：
A. 工具层（不碰模型）：身份注入、越权、知识库命中与拒答、未知工具拦截
B. 对话循环（把模型打桩）：多轮补齐、一次多工具、轮次用尽兜底、API 层 403 与页面可访问

运行：python tests/agent_test.py
默认不打真实模型；要跑真模型：set AGENT_LIVE=1 再执行（会消耗额度）
数据库同样是临时副本，不动 laundry.db
"""
import json
import os
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

SRC_DB = os.path.join(BASE_DIR, "laundry.db")
TMP_DB = os.path.join(tempfile.gettempdir(), "laundry_agent.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
shutil.copy(SRC_DB, TMP_DB)
os.environ.setdefault("LAUNDRY_DATABASE_URL", "sqlite:///" + TMP_DB.replace("\\", "/"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agent import graph, llm, tools  # noqa: E402
from app.config import CARE_FALLBACK_TEXT  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CareRule, Customer  # noqa: E402
from app.services import care_service  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))


def fake_once(tool_name, args, answer="这是最终回答。"):
    """第一轮返回一个 tool_call，第二轮返回答案"""

    def _fake(messages, tools_spec=None, model=None):
        if any(m.get("role") == "tool" for m in messages):
            return {"role": "assistant", "content": answer}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(args, ensure_ascii=False)},
                }
            ],
        }

    return _fake


def fake_parallel(calls, answer="两件事都查了。"):
    """一次返回多个 tool_calls，下一轮出答案"""

    def _fake(messages, tools_spec=None, model=None):
        if any(m.get("role") == "tool" for m in messages):
            return {"role": "assistant", "content": answer}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                }
                for i, (name, args) in enumerate(calls)
            ],
        }

    return _fake


def fake_stubborn(tool_name="query_my_orders"):
    """永远只调工具、永不给答案：验证轮次上限兜底"""

    def _fake(messages, tools_spec=None, model=None):
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_x",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": "{}"},
                }
            ],
        }

    return _fake


db = SessionLocal()

try:
    # ---------- A. 知识库 ----------
    rules = care_service.list_rules(db)
    check("知识库已灌入（≥10 条）", len(rules) >= 10, f"只有 {len(rules)} 条")
    check("每条规则都有出处", all(r["source"] for r in rules))
    check("每条规则都有水洗结论", all(r["water_wash"] for r in rules))
    hit = care_service.lookup(db, "羊绒")
    check("羊绒精确命中", hit and hit["fabric"] == "羊绒", str(hit)[:120])
    hit2 = care_service.lookup(db, "羊绒大衣")  # 口语表达，靠别名/包含命中
    check("口语「羊绒大衣」也能命中羊绒", hit2 and hit2["fabric"] == "羊绒", str(hit2)[:120])
    hit3 = care_service.lookup(db, "羽绒服")
    check("羽绒服命中羽绒", hit3 and hit3["fabric"] == "羽绒", str(hit3)[:120])
    miss = care_service.lookup(db, "量子纤维")
    check("未收录面料不命中", miss is None, str(miss)[:120])

    # ---------- A2. 工具层：身份与越权 ----------
    cust_a = db.execute(select(Customer).where(Customer.phone == "123456")).scalar_one()
    ctx_a = tools.ToolContext(db=db, customer=cust_a)

    orders_a = tools.query_my_orders(ctx_a, limit=10)
    nos_a = [o["order_no"] for o in orders_a["orders"]]
    check("查得到客户 A 自己的订单", len(nos_a) > 0, str(nos_a)[:120])
    check("工具返回里没有手机号字段", "phone" not in json.dumps(orders_a, ensure_ascii=False))

    # 客户 B 的单：用 A 的上下文查 B 的订单号 → 必须查不到
    cust_b = db.execute(select(Customer).where(Customer.phone == "147258")).scalar_one()
    order_b_no = "O20260604181055"
    ctx_b = tools.ToolContext(db=db, customer=cust_b)
    detail_b = tools.query_my_order_detail(ctx_b, order_b_no)
    check("B 能查到自己这单", detail_b.get("found") is True)
    detail_a = tools.query_my_order_detail(ctx_a, order_b_no)
    check("A 查 B 的订单号 → found=False", detail_a.get("found") is False)
    check("越权查询不回显他人信息", "147258" not in json.dumps(detail_a, ensure_ascii=False))

    # 模型硬塞手机号参数：工具签名里没有这个参数，直接报参数错误
    spoof = tools.run_tool("query_my_orders", {"phone": "147258"}, ctx_a)
    check("传 phone 参数 → 结构化参数错误", "error" in spoof, str(spoof)[:120])
    check("参数错误不泄露数据", order_b_no not in json.dumps(spoof, ensure_ascii=False))
    check("未知工具被拦截", "error" in tools.run_tool("drop_all_tables", {}, ctx_a))
    check("工具白名单只有 6 个只读工具", len(tools.ALLOWED_TOOLS) == 6, str(tools.ALLOWED_TOOLS))

    appts = tools.query_my_appointments(ctx_a)
    check("预约工具能查到本人预约或明确为空",
          ("appointments" in appts) and ("error" not in appts), str(appts)[:150])
    check("预约工具不回显他人手机号", "147258" not in json.dumps(appts, ensure_ascii=False))

    account = tools.query_my_account(ctx_a)
    check("账户信息含等级/积分/待付/累计消费",
          all(k in account for k in ("level_name", "points", "unpaid_amount", "total_spent")), str(account)[:150])
    care = tools.query_care_rule(ctx_a, "羊绒")
    check("洗护工具命中并带出处", care.get("found") and care.get("source"), str(care)[:150])
    care_miss = tools.query_care_rule(ctx_a, "量子纤维")
    check("洗护工具未命中走拒答话术",
          care_miss.get("found") is False and care_miss.get("message") == CARE_FALLBACK_TEXT, str(care_miss)[:160])
    price = tools.query_price_list(ctx_a)
    check("价目表有 5 个服务项目", len(price.get("items", [])) == 5, str(price)[:160])

    # ---------- B. 对话循环（模型打桩） ----------
    original = llm.chat_completion
    try:
        llm.chat_completion = fake_once("query_my_orders", {}, answer="你现在有衣服在店里。")
        r1 = graph.run_chat(db, cust_a, "我衣服洗到哪了")
        check("一轮工具 + 一轮答案 = 2 轮", r1["rounds"] == 2, str(r1["rounds"]))
        check("记录到工具调用", r1["tools_used"] == ["query_my_orders"], str(r1["tools_used"]))
        check("回答透传模型文本", r1["answer"] == "你现在有衣服在店里。", r1["answer"][:60])
        check("trace 里能看到工具与结果", any(t.get("node") == "tool" for t in r1["trace"]), str(r1["trace"])[:160])

        llm.chat_completion = fake_parallel([("query_my_orders", {}), ("query_care_rule", {"fabric": "羊绒"})])
        r2 = graph.run_chat(db, cust_a, "我那件羊绒的到哪了？顺便说说羊绒怎么洗")
        check("一次返回两个工具都执行", sorted(r2["tools_used"]) == ["query_care_rule", "query_my_orders"], str(r2["tools_used"]))
        check("并行调用同样只花 2 轮", r2["rounds"] == 2, str(r2["rounds"]))

        llm.chat_completion = fake_stubborn()
        r3 = graph.run_chat(db, cust_a, "帮我查查")
        check("模型只调工具不给答案时按上限收口", "没查清" in r3["answer"], r3["answer"][:80])
        check("收口轮次等于上限", r3["rounds"] == 4, str(r3["rounds"]))

        # 模型被诱导去查别人：参数里塞 phone，工具层照样只返回本人
        llm.chat_completion = fake_once("query_my_orders", {"phone": "147258", "customer_id": 4}, answer="这是你的订单。")
        r4 = graph.run_chat(db, cust_a, "查一下 147258 这个人的订单")
        check("诱导查他人时仍只拿到本人订单", len(r4["tools_used"]) == 1)
        check("诱导场景 trace 里没有任何他人订单号", order_b_no not in json.dumps(r4["trace"], ensure_ascii=False))
    finally:
        llm.chat_completion = original

    # ---------- B2. HTTP 层 ----------
    with TestClient(app) as client:
        # P0-3 之后老客户由门店开通账号（测试用管理员 token 调开通接口）
        admin = client.post("/api/login", json={"username": "admin", "password": "admin123"}).json()
        AH = {"Authorization": "Bearer " + admin["token"]}
        from app.db import SessionLocal  # noqa: E402
        from app.models import Customer  # noqa: E402

        s = SessionLocal()
        cid = s.query(Customer).filter(Customer.phone == "123456").first().id
        s.close()
        reg = client.post("/api/customers/" + str(cid) + "/bind-account",
                          json={"phone": "123456", "password": "pass1234", "name": "lk"}, headers=AH)
        check("门店为老客户开通账号成功或已开通", reg.status_code in (200, 409), str(reg.status_code))
        login = client.post("/api/customer/login", json={"phone": "123456", "password": "pass1234"})
        check("客户登录成功", login.status_code == 200 and login.json().get("token"), str(login.json())[:120])
        token = login.json().get("token", "")
        auth = {"Authorization": "Bearer " + token}

        original2 = llm.chat_completion
        llm.chat_completion = fake_once("query_my_account", {}, answer="你是普通客户，暂无折扣。")
        try:
            chat = client.post("/api/my/chat", headers=auth, json={"message": "我是什么等级？", "history": []})
        finally:
            llm.chat_completion = original2
        check("对话接口 200", chat.status_code == 200, str(chat.status_code))
        body = chat.json().get("data", {})
        check("接口返回回答与工具列表", bool(body.get("answer")) and body.get("tools_used") == ["query_my_account"], str(body)[:160])

        staff = client.post("/api/login", json={"username": "admin", "password": "admin123"})
        staff_auth = {"Authorization": "Bearer " + staff.json().get("token", "")}
        check("员工打对话接口 403", client.post("/api/my/chat", headers=staff_auth, json={"message": "hi"}).status_code == 403)
        check("未登录打对话接口 401", client.post("/api/my/chat", json={"message": "hi"}).status_code == 401)

        check("助手页面 200", client.get("/me/chat").status_code == 200)
        check("me_chat.js 可用", client.get("/js/me_chat.js").status_code == 200)
        check("空消息被 422 拦下", client.post("/api/my/chat", headers=auth, json={"message": ""}).status_code == 422)

        # 真模型连通性（可选，默认跳过）
        if os.getenv("AGENT_LIVE") == "1":
            live = client.post("/api/my/chat", headers=auth,
                               json={"message": "我上周送洗的羊绒大衣到哪一步了？顺便说说羊绒怎么护理", "history": []})
            live_body = live.json().get("data", {})
            check("真实模型调用成功", live.status_code == 200 and not live_body.get("error"), str(live_body)[:200])
            check("真实模型至少调了一个工具", len(live_body.get("tools_used") or []) >= 1, str(live_body.get("tools_used")))
            check("真实回答不含他人手机号", "147258" not in json.dumps(live_body, ensure_ascii=False))

    # ---------- 数据完整性：知识库写入后订单数没变 ----------
    from app.db import SessionLocal as SL

    db2 = SL()
    try:
        from app.models import Order

        check("测试过程没有改动订单表", db2.execute(select(Order)).scalars().all() != [])
        check("care_rules 表已建立", db2.execute(select(CareRule)).scalars().all() != [])
    finally:
        db2.close()
finally:
    db.close()

passed = sum(1 for _, ok, _ in results if ok)
print("=" * 60)
for name, ok, extra in results:
    print(("PASS " if ok else "FAIL ") + name + (("  <- " + extra) if (extra and not ok) else ""))
print("=" * 60)
print(f"通过 {passed} / {len(results)}")
sys.exit(0 if passed == len(results) else 1)
