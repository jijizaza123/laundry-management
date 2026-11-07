"""Agent 出口：默认手写循环；AGENT_ENGINE=langgraph 时换成 LangGraph 版

两个引擎共用同一份 SYSTEM_PROMPT / 工具白名单 / run_tool，
所以换引擎不会带来行为差异——tests/langgraph_test.py 会按住这一点。
"""
from ..config import AGENT_ENGINE
from .graph import run_chat as _run_chat_loop
from .staff_graph import run_staff_chat  # noqa: F401


def run_chat(db, customer, message, history=None, model=None):
    if AGENT_ENGINE == "langgraph":
        from .graph_lg import run_chat_lg

        return run_chat_lg(db=db, customer=customer, message=message, history=history, model=model)
    return _run_chat_loop(db=db, customer=customer, message=message, history=history, model=model)


__all__ = ["run_chat", "run_staff_chat"]
