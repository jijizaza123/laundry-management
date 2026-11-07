"""登录失败限流：同一账号 + 同一来源，窗口内错太多次就锁一会儿

实现说明（面试也会被问）：进程内存计数，单进程够用；
多进程/多机部署时必须换成 Redis 或网关层限流，否则各进程各算各的。
"""
import time
from collections import defaultdict

from ..config import LOGIN_LOCK_SECONDS, LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS

_FAILURES: dict[str, list[float]] = defaultdict(list)
_LOCKED_UNTIL: dict[str, float] = {}


def _key(scope: str, account: str) -> str:
    return (scope or "staff") + ":" + (account or "").strip().lower()


def check(scope: str, account: str) -> dict:
    key = _key(scope, account)
    locked_until = _LOCKED_UNTIL.get(key, 0)
    now = time.time()
    if locked_until > now:
        return {
            "allowed": False,
            "message": "失败次数过多，请 " + str(int(locked_until - now) + 1) + " 秒后再试",
        }
    return {"allowed": True, "message": ""}


def record_failure(scope: str, account: str) -> None:
    key = _key(scope, account)
    now = time.time()
    window_start = now - LOGIN_WINDOW_SECONDS
    hits = [t for t in _FAILURES.get(key, []) if t >= window_start]
    hits.append(now)
    _FAILURES[key] = hits
    if len(hits) >= LOGIN_MAX_FAILURES:
        _LOCKED_UNTIL[key] = now + LOGIN_LOCK_SECONDS
        _FAILURES[key] = []


def reset(scope: str, account: str) -> None:
    key = _key(scope, account)
    _FAILURES.pop(key, None)
    _LOCKED_UNTIL.pop(key, None)


def reset_all() -> None:
    """测试用：清空全部计数"""
    _FAILURES.clear()
    _LOCKED_UNTIL.clear()
