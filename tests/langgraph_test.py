"""LangGraph 引擎对照测试

目的不是"再测一遍功能"，而是证明换引擎后行为完全一致：
同样的打桩模型，手写循环和 LangGraph 版本必须给出同样的 rounds / tools_used / 收口话术。
数据库仍是临时副本，不动 laundry.db。

运行：python tests/langgraph_test.py
"""
import json
import os
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

SRC_DB = os.path.join(BASE_DIR, "laundry.db")
TMP_DB = os.path.join(tempfile.gettempdir(), "laundry_lg.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
shutil.copy(SRC_DB, TMP_DB)
os.environ.setdefault("LAUNDRY_DATABASE_URL", "sqlite:///" + TMP_DB.replace("\\", "/"))

from sqlalchemy import select  # noqa: E402

from app.agent import graph, graph_lg, llm  # noqa: E402
from app.agent.staff_graph import run_staff_chat  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Customer, User  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))


def fake_once(tool_name, args, answer="这是最终回答。"):
    def _fake(messages, tools_spec=None, model=None):
        if any(m.get("role") == "tool" for m in messages):
            return {"role": "assistant", "content": answer}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": tool_name, "arguments": json.dumps(args, ensure_ascii=False)}}
            ],
        }

    return _fake


def fake_parallel(calls, answer="两件事都查了。"):
    def _fake(messages, tools_spec=None, model=None):
        if any(m.get("role") == "tool" for m in messages):
            return {"role": "assistant", "content": answer}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": f"call_{i}", "type": "function",
                 "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
                for i, (name, args) in enumerate(calls)
            ],
        }

    return _fake


def fake_stubborn(tool_name="query_my_orders"):
    def _fake(messages, tools_spec=None, model=None):
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_x", "type": "function",
                 "function": {"name": tool_name, "arguments": "{}"}}
            ],
        }

    return _fake


def fake_broken(messages, tools_spec=None, model=None):
    raise llm.AgentError("模型服务超时，请稍后再问一次。")


db = SessionLocal()
try:
    cust = db.execute(select(Customer).where(Customer.phone == "123456")).scalar_one()
    admin = db.execute(select(User).where(User.username == "admin")).scalar_one()

    original = llm.chat_completion
    try:
        # ---------- 1. 单工具：两个引擎结果一致 ----------
        llm.chat_completion = fake_once("query_my_orders", {}, answer="你现在有衣服在店里。")
        loop_r = graph.run_chat(db, cust, "我衣服洗到哪了")
        lg_r = graph_lg.run_chat_lg(db, cust, "我衣服洗到哪了")
        check("单工具：轮次一致", loop_r["rounds"] == lg_r["rounds"] == 2,
              f"loop={loop_r['rounds']} lg={lg_r['rounds']}")
        check("单工具：工具列表一致", loop_r["tools_used"] == lg_r["tools_used"] == ["query_my_orders"],
              str(lg_r["tools_used"]))
        check("单工具：回答一致", loop_r["answer"] == lg_r["answer"] == "你现在有衣服在店里。", lg_r["answer"][:60])
        check("单工具：trace 里有 tool 节点", any(t.get("node") == "tool" for t in lg_r["trace"]),
              str(lg_r["trace"])[:160])
        check("返回结构齐全",
              all(k in lg_r for k in ("answer", "trace", "rounds", "tools_used", "error")), str(lg_r.keys()))

        # ---------- 2. 一次多工具 ----------
        llm.chat_completion = fake_parallel([("query_my_orders", {}), ("query_care_rule", {"fabric": "羊绒"})])
        loop_p = graph.run_chat(db, cust, "我那件羊绒的到哪了？顺便说说羊绒怎么洗")
        lg_p = graph_lg.run_chat_lg(db, cust, "我那件羊绒的到哪了？顺便说说羊绒怎么洗")
        check("多工具：两个都执行", sorted(lg_p["tools_used"]) == ["query_care_rule", "query_my_orders"],
              str(lg_p["tools_used"]))
        check("多工具：仍只花 2 轮", lg_p["rounds"] == 2, str(lg_p["rounds"]))
        check("多工具：与手写循环一致",
              sorted(loop_p["tools_used"]) == sorted(lg_p["tools_used"]) and loop_p["rounds"] == lg_p["rounds"],
              f"loop={loop_p['tools_used']} lg={lg_p['tools_used']}")

        # ---------- 3. 只调工具不给答案：按上限收口 ----------
        llm.chat_completion = fake_stubborn()
        loop_s = graph.run_chat(db, cust, "帮我查查")
        lg_s = graph_lg.run_chat_lg(db, cust, "帮我查查")
        check("死循环：按上限收口", "没查清" in lg_s["answer"], lg_s["answer"][:80])
        check("死循环：轮次等于上限", lg_s["rounds"] == 4, str(lg_s["rounds"]))
        check("死循环：收口语与手写循环一致", lg_s["answer"] == loop_s["answer"], lg_s["answer"][:60])

        # ---------- 4. 越权诱导：参数里塞 phone 也不出他人数据 ----------
        llm.chat_completion = fake_once("query_my_orders", {"phone": "147258", "customer_id": 4}, answer="这是你的订单。")
        lg_x = graph_lg.run_chat_lg(db, cust, "查一下 147258 这个人的订单")
        check("越权诱导：只走本人工具", lg_x["tools_used"] == ["query_my_orders"], str(lg_x["tools_used"]))
        check("越权诱导：trace 不含他人订单号", "O20260604181055" not in json.dumps(lg_x["trace"], ensure_ascii=False))

        # ---------- 5. 模型报错：走统一错误文案 ----------
        llm.chat_completion = fake_broken
        lg_e = graph_lg.run_chat_lg(db, cust, "查订单")
        check("模型报错：error=True", lg_e["error"] is True, str(lg_e)[:120])
        check("模型报错：给出可读文案", "超时" in lg_e["answer"], lg_e["answer"][:60])

        # ---------- 6. 空消息与历史裁剪 ----------
        llm.chat_completion = fake_once("query_my_account", {}, answer="你是普通会员。")
        lg_empty = graph_lg.run_chat_lg(db, cust, "   ")
        check("空消息直接反问，不调模型", lg_empty["rounds"] == 0 and lg_empty["tools_used"] == [], str(lg_empty)[:100])

        big_history = [{"role": "user", "content": "x" * 2000}, {"role": "assistant", "content": "y" * 2000}] * 10
        lg_h = graph_lg.run_chat_lg(db, cust, "我是什么等级", history=big_history)
        check("历史被裁剪后仍能跑完", lg_h["answer"] == "你是普通会员。", lg_h["answer"][:60])
    finally:
        llm.chat_completion = original

    # ---------- 7. 员工引擎没被换掉：写操作仍是两段式 ----------
    check("员工 Agent 仍是手写图（不依赖 langgraph）",
          run_staff_chat(db, admin, "确认执行", [], confirm_action_id="act_not_exist")["error"] is True)

    # ---------- 8. 引擎开关 ----------
    check("配置文件里有 AGENT_ENGINE 开关", "AGENT_ENGINE" in open(os.path.join(BASE_DIR, "app", "config.py"), encoding="utf-8").read())
    import app.agent as agent_pkg  # noqa: E402

    check("默认引擎是手写循环", agent_pkg.run_chat.__module__ == "app.agent", agent_pkg.run_chat.__module__)
finally:
    db.close()

passed = sum(1 for _, ok, _ in results if ok)
print("=" * 60)
for name, ok, extra in results:
    print(("PASS " if ok else "FAIL ") + name + (("  <- " + extra) if (extra and not ok) else ""))
print("=" * 60)
print(f"通过 {passed} / {len(results)}")
sys.exit(0 if passed == len(results) else 1)
