"""客户端 Agent 的 LangGraph 版本：同一份逻辑，节点/边显式化

    plan ──有 tool_calls──▶ act ──工具结果回填──▶ plan
      └──── 无 tool_calls ────▶ END(出答案)

对外契约和 graph.run_chat 完全一致：{answer, trace, rounds, tools_used, error}。
默认引擎仍是 graph.run_chat（手写循环），设置 AGENT_ENGINE=langgraph 才走这里；
两条路共用同一份 SYSTEM_PROMPT / TOOL_SPECS / run_tool，避免"两套代码两种行为"。
"""
import json
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from ..config import AGENT_MAX_ROUNDS, CARE_FALLBACK_TEXT
from ..models import Customer
from . import llm
from .graph import SYSTEM_PROMPT, _safe_args, _trim_history
from .tools import TOOL_SPECS, ToolContext, run_tool

class AgentState(TypedDict, total=False):
    """messages/trace/tools_used 用加法归并，其余字段直接覆盖"""

    messages: Annotated[list, operator.add]
    trace: Annotated[list, operator.add]
    tools_used: Annotated[list, operator.add]
    rounds: int
    answer: str
    error: bool
    done: bool
    calls: list


GIVE_UP_TEXT = "这个问题我查了几轮还没查清，先别急，你可以直接看「我的订单」页面，或者到店问一下师傅。"


def _build_graph(ctx: ToolContext, model: str | None):
    """把 db/customer 关在闭包里，状态里只放对话相关的东西"""

    def plan(state: dict) -> dict:
        round_index = state["rounds"] + 1
        try:
            assistant = llm.chat_completion(state["messages"], TOOL_SPECS, model=model)
        except llm.AgentError as exc:
            return {"answer": str(exc), "error": True, "done": True, "rounds": round_index}

        calls = assistant.get("tool_calls") or []
        content = (assistant.get("content") or "").strip()

        if not calls:
            answer = content or CARE_FALLBACK_TEXT
            return {
                "answer": answer,
                "done": True,
                "rounds": round_index,
                "trace": [{"round": round_index, "node": "answer", "content": answer[:200]}],
            }

        return {
            "calls": calls,
            "rounds": round_index,
            "messages": [
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
                        for i, call in enumerate(calls)
                    ],
                }
            ],
        }

    def act(state: dict) -> dict:
        round_index = state["rounds"]
        new_messages, new_trace, used = [], [], []
        for position, call in enumerate(state.get("calls") or []):
            name = call.get("function", {}).get("name", "")
            args = _safe_args(call.get("function", {}).get("arguments"))
            result = run_tool(name, args, ctx)
            used.append(name)
            new_trace.append(
                {
                    "round": round_index,
                    "node": "tool",
                    "tool": name,
                    "args": args,
                    "result_preview": json.dumps(result, ensure_ascii=False)[:220],
                }
            )
            new_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"call_{round_index}_{position}",
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False)[:4000],
                }
            )
        return {"messages": new_messages, "trace": new_trace, "tools_used": used, "calls": []}

    def route(state: dict) -> str:
        if state.get("done"):
            return END
        # 先判轮次上限，再判有没有待执行的工具调用——否则模型一直只调工具会绕成死循环
        if state["rounds"] >= AGENT_MAX_ROUNDS:
            return "give_up"
        if state.get("calls"):
            return "act"
        return "plan"

    def give_up(state: dict) -> dict:
        return {
            "answer": GIVE_UP_TEXT,
            "done": True,
            "trace": [{"round": AGENT_MAX_ROUNDS, "node": "give_up"}],
        }

    graph = StateGraph(AgentState)
    graph.add_node("plan", plan)
    graph.add_node("act", act)
    graph.add_node("give_up", give_up)
    graph.set_entry_point("plan")
    graph.add_conditional_edges("plan", route, {"act": "act", "plan": "plan", "give_up": "give_up", END: END})
    graph.add_edge("act", "plan")
    graph.add_edge("give_up", END)
    return graph.compile()


def run_chat_lg(
    db: Session,
    customer: Customer,
    message: str,
    history: list[dict] | None = None,
    model: str | None = None,
) -> dict:
    """跑一轮完整对话（LangGraph 引擎），返回结构同 graph.run_chat"""
    text = (message or "").strip()
    if not text:
        return {"answer": "你想问什么？比如“我衣服洗到哪了”，或者“羊绒大衣怎么洗”。", "trace": [], "rounds": 0, "tools_used": []}

    ctx = ToolContext(db=db, customer=customer)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += _trim_history(history)
    messages.append({"role": "user", "content": text[:800]})

    graph = _build_graph(ctx, model)
    final = graph.invoke({"messages": messages, "trace": [], "tools_used": [], "rounds": 0, "answer": "", "error": False, "done": False})

    return {
        "answer": final.get("answer") or CARE_FALLBACK_TEXT,
        "trace": final.get("trace") or [],
        "rounds": final.get("rounds") or 0,
        "tools_used": final.get("tools_used") or [],
        "error": bool(final.get("error")),
    }
