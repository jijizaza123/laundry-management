"""Agnes（OpenAI 兼容）模型调用封装

只做一件事：把 messages + tools 发出去，拿回一条 assistant message。
网络错误、没有 key、返回格式不对，统一抛 AgentError，由上层转成人话。
"""
import uuid

import httpx

from ..config import AGNES_API_KEY, AGNES_BASE_URL, AGNES_MODEL, AGENT_TIMEOUT


class AgentError(RuntimeError):
    """Agent 层的可读错误，上层直接展示给用户"""


def is_configured() -> bool:
    return bool(AGNES_API_KEY)


def chat_completion(messages: list[dict], tools: list[dict] | None = None, model: str | None = None) -> dict:
    if not AGNES_API_KEY:
        raise AgentError("还没有配置模型密钥：请在项目根目录的 .env 里填 AGNES_API_KEY")

    payload: dict = {
        "model": model or AGNES_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    # 这条链路冷启动偶发很慢（实测单次 15s~70s 都有），超时重试一次再报错
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            resp = httpx.post(
                AGNES_BASE_URL + "/chat/completions",
                headers={
                    "Authorization": "Bearer " + AGNES_API_KEY,
                    "Content-Type": "application/json",
                    # 每轮带独立的请求 id：上游网关按 id 做缓存，缺了会出现"答非所问"的串响应
                    "X-Request-Id": uuid.uuid4().hex,
                },
                json=payload,
                timeout=AGENT_TIMEOUT,
            )
            break
        except httpx.TimeoutException as exc:
            last_error = exc
            continue
        except httpx.HTTPError as exc:
            raise AgentError(f"连接模型服务失败：{type(exc).__name__}") from None
    else:
        raise AgentError("模型响应超时了（已重试一次），稍后再问一句") from last_error

    if resp.status_code == 401:
        raise AgentError("模型密钥无效，请检查 .env 里的 AGNES_API_KEY")
    if resp.status_code == 404:
        raise AgentError(f"模型 {payload['model']} 不可用，请在 .env 里换一个 AGNES_MODEL")
    if resp.status_code != 200:
        raise AgentError(f"模型服务返回 {resp.status_code}，先别急，稍后再试")

    try:
        message = resp.json()["choices"][0]["message"]
    except (KeyError, IndexError, ValueError):
        raise AgentError("模型返回格式异常，稍后再试") from None
    return message
