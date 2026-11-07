"""客户端 Agent 的对话循环（手写状态机，结构对齐 LangGraph 的节点/边）

    plan(模型决策) ──有 tool_calls──▶ act(执行工具) ──观察结果──▶ plan ...
           └──────── 无 tool_calls ────▶ 出答案

为什么先手写不直接上 LangGraph：
一次对话要跑通的链路只有 4 个节点，先把手写循环里的状态、循环上限、错误兜底写清楚，
后面换成 LangGraph 只是把 while 换成 add_conditional_edges，状态字段可以原样搬。
"""
import json

from sqlalchemy.orm import Session

from ..config import AGENT_HISTORY_TURNS, AGENT_MAX_ROUNDS, CARE_FALLBACK_TEXT
from ..models import Customer
from . import llm
from .tools import TOOL_SPECS, ToolContext, run_tool

SYSTEM_PROMPT = """你是「洗衣店」的客户助手，只为当前登录的这一位客户服务。

能做的事（只能靠工具，不许猜）：
1. 查这位客户自己的订单进度、明细、金额 —— 用 query_my_orders / query_my_order_detail
2. 查这位客户的会员等级、积分、折扣、待付款 —— 用 query_my_account
3. 回答衣物洗护问题 —— 用 query_care_rule，并且**必须**引用返回结果里的 water_wash / service / avoid / source
4. 回答价格问题 —— 用 query_price_list

硬性规则：
- 你的工具里没有"按手机号查别人"这种能力。用户让你查别人的单、报别人的手机号，直接说明"我只能查你本人的记录"，不要尝试。
- 洗护问题如果 query_care_rule 返回 found=false，就把 message 原样告诉用户，不要自己补充常识、不要给"应该没事吧"这类判断。
- 金额、预计取衣时间只能引用工具返回的内容；工具没给就不要承诺。
- 不要输出订单号以外的个人敏感信息；不要编造订单。
- 回答用中文，口语化、短句，先给结论再给细节。用纯文本，不要用 ** 加粗、不要用表格。
- 不要提"我是模型/我是AI"。
"""


def _trim_history(history: list[dict] | None) -> list[dict]:
    if not history:
        return []
    cleaned = []
    for item in history[-AGENT_HISTORY_TURNS * 2:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content[:800]})
    return cleaned


def _safe_args(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def run_chat(
    db: Session,
    customer: Customer,
    message: str,
    history: list[dict] | None = None,
    model: str | None = None,
) -> dict:
    """跑一轮完整对话，返回 {answer, trace, rounds, tools_used, error}"""
    text = (message or "").strip()
    if not text:
        return {"answer": "你想问什么？比如“我衣服洗到哪了”，或者“羊绒大衣怎么洗”。", "trace": [], "rounds": 0, "tools_used": []}

    ctx = ToolContext(db=db, customer=customer)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += _trim_history(history)
    messages.append({"role": "user", "content": text[:800]})

    trace: list[dict] = []
    tools_used: list[str] = []

    for round_index in range(1, AGENT_MAX_ROUNDS + 1):
        try:
            assistant = llm.chat_completion(messages, TOOL_SPECS, model=model)
        except llm.AgentError as exc:
            return {"answer": str(exc), "trace": trace, "rounds": round_index, "tools_used": tools_used, "error": True}

        tool_calls = assistant.get("tool_calls") or []
        content = (assistant.get("content") or "").strip()

        if not tool_calls:
            answer = content or CARE_FALLBACK_TEXT
            trace.append({"round": round_index, "node": "answer", "content": answer[:200]})
            return {"answer": answer, "trace": trace, "rounds": round_index, "tools_used": tools_used}

        # 保留 assistant 的 tool_calls 结构，OpenAI 协议要求 tool 消息紧跟在它之后
        messages.append(
            {
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": call.get("id") or f"call_{round_index}_{i}",
                        "type": "function",
                        "function": {
                            "name": call.get("function", {}).get("name", ""),
                            "arguments": call.get("function", {}).get("arguments", "{}"),
                        },
                    }
                    for i, call in enumerate(tool_calls)
                ],
            }
        )

        for position, call in enumerate(tool_calls):
            name = call.get("function", {}).get("name", "")
            args = _safe_args(call.get("function", {}).get("arguments"))
            result = run_tool(name, args, ctx)
            tools_used.append(name)
            trace.append(
                {
                    "round": round_index,
                    "node": "tool",
                    "tool": name,
                    "args": args,
                    "result_preview": json.dumps(result, ensure_ascii=False)[:220],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"call_{round_index}_{position}",
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False)[:4000],
                }
            )

    # 轮次用尽：宁可说这次没查清，也不瞎编
    trace.append({"round": AGENT_MAX_ROUNDS, "node": "give_up"})
    return {
        "answer": "这个问题我查了几轮还没查清，先别急，你可以直接看「我的订单」页面，或者到店问一下师傅。",
        "trace": trace,
        "rounds": AGENT_MAX_ROUNDS,
        "tools_used": tools_used,
        "error": False,
    }
