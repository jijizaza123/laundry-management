"""管理端 Agent 的对话循环（和客户端同一套结构，只是工具箱与提示词换成本店员工视角）

写操作的关键：模型只能"提议"，不能"执行"。propose_* 返回带 action_id 的动作卡，
员工在页面上点确认，才带着 action_id 回到 /api/staff/chat 真正落库。
"""
import json

from sqlalchemy.orm import Session

from ..config import AGENT_HISTORY_TURNS, AGENT_MAX_ROUNDS
from ..models import User
from . import llm
from .staff_tools import execute_action, run_staff_tool

SYSTEM_PROMPT = """你是「洗衣店」的员工助手，服务对象是门店员工（不是客户）。

能做的事（只能靠工具，不许猜）：
1. 查订单：query_orders（可按状态/关键词筛）、query_order_detail（按订单号）
2. 查经营情况：query_today_overview（今日收衣、在店、可取、今日收入）
3. 查待复核：query_review_pending（客户线上单还没复核的）
4. 查客户：query_customer（按手机号精确查一位）
5. 洗护规则：query_care_rule
6. 价目表：query_price_list
7. 写操作只有三个"提议"：propose_create_order / propose_change_status / propose_complete_order

硬性规则：
- 写操作绝对不能假装已经完成。调用 propose_* 之后，必须告诉员工"我已经准备好动作卡，你点确认才会执行"。
- 金额、件数、状态、时间只能引用工具返回的内容；工具没给就说不知道，不要估。
- query_care_rule 返回 found=false 时原样转述"规则库里没有这个面料"，不要自己补常识。
- 客户手机号只在员工明确要查这位客户时使用，不要主动罗列一批客户信息。
- 回答用中文、短句、先结论后细节，纯文本，不要 ** 加粗，不要表格。
- 不要提"我是模型/我是AI"。
"""

STAFF_TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "query_orders",
        "description": "查订单列表，可按状态和关键词筛。状态：received 已收衣 / washing 洗涤中 / ready 可取衣 / completed 已完成 / cancelled 已取消",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "description": "订单状态，可省略"},
            "keyword": {"type": "string", "description": "订单号/客户姓名/手机号关键词，可省略"},
            "limit": {"type": "integer", "description": "返回条数，默认 10"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "query_order_detail",
        "description": "按订单号查一单的明细、金额、状态、复核情况",
        "parameters": {"type": "object", "properties": {
            "order_no": {"type": "string", "description": "订单号，例如 20261107123456"},
        }, "required": ["order_no"]},
    }},
    {"type": "function", "function": {
        "name": "query_today_overview",
        "description": "今日概览：收衣数、在店数、可取衣数、今日收入、逾期未取",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "query_review_pending",
        "description": "客户线上下的单里，还没复核或还没被客户确认金额的",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "query_customer",
        "description": "按手机号精确查一位客户的等级、积分、地址（只查一位，不做模糊搜索）",
        "parameters": {"type": "object", "properties": {
            "phone": {"type": "string", "description": "客户手机号（完整）"},
        }, "required": ["phone"]},
    }},
    {"type": "function", "function": {
        "name": "query_care_rule",
        "description": "查某个面料的洗护规则（能否水洗、禁忌、依据）",
        "parameters": {"type": "object", "properties": {
            "fabric": {"type": "string", "description": "面料名，例如 羊绒 / 真丝 / 羽绒"},
        }, "required": ["fabric"]},
    }},
    {"type": "function", "function": {
        "name": "query_price_list",
        "description": "查服务价目表（服务名与单价）",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "propose_create_order",
        "description": "提议给客户下单（不会立即执行，返回待确认动作卡）",
        "parameters": {"type": "object", "properties": {
            "customer_phone": {"type": "string", "description": "客户手机号"},
            "items": {"type": "string", "description": "衣物明细文本，例如 外套-干洗×2"},
            "deposit": {"type": "number", "description": "预收定金，可省略"},
        }, "required": ["customer_phone", "items"]},
    }},
    {"type": "function", "function": {
        "name": "propose_change_status",
        "description": "提议改订单状态（不会立即执行，返回待确认动作卡）",
        "parameters": {"type": "object", "properties": {
            "order_no": {"type": "string", "description": "订单号"},
            "status": {"type": "string", "description": "目标状态：received/washing/ready/completed/cancelled"},
        }, "required": ["order_no", "status"]},
    }},
    {"type": "function", "function": {
        "name": "propose_complete_order",
        "description": "提议取衣结算（不会立即执行，返回待确认动作卡）",
        "parameters": {"type": "object", "properties": {
            "order_no": {"type": "string", "description": "订单号"},
            "pay_amount": {"type": "number", "description": "本次收款金额，可省略（省略就按待收金额结算）"},
        }, "required": ["order_no"]},
    }},
]


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


def _safe_args(raw) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _pending_from_trace(trace: list[dict]) -> list[dict]:
    """把工具返回的动作卡挑出来，交给前端渲染确认按钮"""
    cards = []
    for step in trace:
        payload = step.get("_raw")
        if isinstance(payload, dict) and payload.get("data", {}).get("action_id"):
            cards.append(
                {
                    "action_id": payload["data"]["action_id"],
                    "summary": payload["data"].get("summary", ""),
                    "tool": step.get("tool", ""),
                }
            )
    return cards


class _Ctx:
    """员工工具上下文：db + 当前员工（写操作要记经手人）"""

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user


def _describe_executed(data: dict) -> str:
    """把执行结果说成人话，别把 JSON 直接糊到聊天框里"""
    kind = data.get("executed")
    if kind == "create_order":
        return f"已开单：{data.get('order_no')}，金额 ¥{float(data.get('total') or 0):.2f}。"
    if kind == "change_status":
        return f"已执行：订单 {data.get('order_no')} 状态改为「{data.get('status')}」。"
    if kind == "complete_order":
        points = data.get("points") or {}
        tail = f"，客户加 {points.get('added')} 分" if points.get("added") else ""
        return f"已结算：订单 {data.get('order_no')}，收款 ¥{float(data.get('settled') or 0):.2f}{tail}。"
    return "已执行。"


def run_staff_chat(
    db: Session,
    user: User,
    message: str,
    history: list[dict] | None = None,
    confirm_action_id: str | None = None,
    model: str | None = None,
) -> dict:
    # 1) 员工点了"确认"：直接执行之前暂存的动作
    if confirm_action_id:
        result = execute_action(db, user, confirm_action_id)
        if not result.get("ok"):
            return {"answer": "没执行成功：" + str(result.get("error")), "trace": [], "rounds": 1,
                    "tools_used": [], "pending_actions": [], "error": True}
        data = result["data"]
        summary = _describe_executed(data)
        return {"answer": summary, "trace": [{"round": 1, "node": "confirm", "content": summary[:200]}],
                "rounds": 1, "tools_used": [data.get("executed", "")], "pending_actions": [], "error": False}

    text = (message or "").strip()
    if not text:
        return {"answer": "要查什么？比如“今天收了几件”“帮我看看待复核的单”。", "trace": [], "rounds": 0,
                "tools_used": [], "pending_actions": [], "error": False}

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += _trim_history(history)
    messages.append({"role": "user", "content": text[:800]})

    trace: list[dict] = []
    tools_used: list[str] = []

    for round_index in range(1, AGENT_MAX_ROUNDS + 1):
        try:
            assistant = llm.chat_completion(messages, STAFF_TOOL_SPECS, model=model)
        except llm.AgentError as exc:
            return {"answer": str(exc), "trace": trace, "rounds": round_index, "tools_used": tools_used,
                    "pending_actions": _pending_from_trace(trace), "error": True}

        tool_calls = assistant.get("tool_calls") or []
        content = (assistant.get("content") or "").strip()

        if not tool_calls:
            answer = content or "我没查到依据，你先在订单页确认一下，或者告诉我具体订单号。"
            trace.append({"round": round_index, "node": "answer", "content": answer[:200]})
            return {"answer": answer, "trace": trace, "rounds": round_index, "tools_used": tools_used,
                    "pending_actions": _pending_from_trace(trace), "error": False}

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
            result = run_staff_tool(_Ctx(db, user), name, args)
            tools_used.append(name)
            trace.append(
                {
                    "round": round_index,
                    "node": "tool",
                    "tool": name,
                    "args": args,
                    "result_preview": json.dumps(result, ensure_ascii=False)[:220],
                    "_raw": result if isinstance(result, dict) else None,
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

    trace.append({"round": AGENT_MAX_ROUNDS, "node": "give_up"})
    return {"answer": "我查了几轮还没查清，你给个订单号我再查一次。", "trace": trace, "rounds": AGENT_MAX_ROUNDS,
            "tools_used": tools_used, "pending_actions": _pending_from_trace(trace), "error": False}


class _Ctx:
    """员工工具上下文：db + 当前员工（写操作要记经手人）"""

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
