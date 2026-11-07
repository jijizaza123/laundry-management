"""接口压测：给"并发下到底能扛多少"一个自己的数字

不引 locust（少一个依赖、少一个配置），用线程 + httpx 直接打：
  python scripts/load_test.py --base-url http://127.0.0.1:7778 --users 20 --iters 40

输出：QPS、P50/P95/P99、错误率，按接口分组。
注意：SQLite 单文件在写并发下会锁表，这份报告正是用来暴露这个上限的。
"""
import argparse
import statistics
import sys
import threading
import time
from collections import defaultdict

import httpx

TARGETS = [
    ("login", "POST", "/api/login", {"username": "admin", "password": "admin123"}, False),
    ("orders", "GET", "/api/orders", None, True),
    ("stats", "GET", "/api/stats", None, True),
    ("my_orders", "GET", "/api/my/orders", None, "customer"),
    ("quote", "POST", "/api/my/quote", {"items_detail": [{"category": "上衣", "service_name": "普通洗", "quantity": 2}]}, "customer"),
]

records = defaultdict(list)
errors = defaultdict(int)
lock = threading.Lock()


def one_client(base, staff_token, customer_token, iters, barrier):
    headers_staff = {"Authorization": "Bearer " + staff_token} if staff_token else {}
    headers_customer = {"Authorization": "Bearer " + customer_token} if customer_token else {}
    barrier.wait()
    with httpx.Client(base_url=base, timeout=20) as client:
        for _ in range(iters):
            for name, method, path, payload, auth in TARGETS:
                headers = headers_staff if auth is True else (headers_customer if auth == "customer" else {})
                started = time.perf_counter()
                try:
                    if method == "GET":
                        r = client.get(path, headers=headers)
                    else:
                        r = client.post(path, json=payload, headers=headers)
                    ms = (time.perf_counter() - started) * 1000
                    ok = r.status_code < 400
                except Exception:
                    ms = (time.perf_counter() - started) * 1000
                    ok = False
                with lock:
                    records[name].append(ms)
                    if not ok:
                        errors[name] += 1


def pct(values, p):
    if not values:
        return 0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * p))))
    return values[idx]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:7778")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--customer-phone", default="123456")
    parser.add_argument("--customer-password", default="pass1234")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=20) as client:
        r = client.post("/api/login", json={"username": "admin", "password": "admin123"})
        if r.status_code != 200:
            print("管理员登录失败，压测需要先跑起服务并确认账号：" + str(r.text)[:200])
            return 2
        staff_token = r.json()["token"]
        r = client.post("/api/customer/login", json={"phone": args.customer_phone, "password": args.customer_password})
        customer_token = r.json().get("token", "") if r.status_code == 200 else ""
        if not customer_token:
            print("客户登录失败（用临时库时先给该手机号开通账号）：" + str(r.text)[:200])

    barrier = threading.Barrier(args.users)
    threads = [
        threading.Thread(target=one_client, args=(args.base_url, staff_token, customer_token, args.iters, barrier))
        for _ in range(args.users)
    ]
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - started

    total = sum(len(v) for v in records.values())
    print("=" * 68)
    print(f"并发 {args.users} × 轮次 {args.iters}，请求总数 {total}，耗时 {wall:.2f}s，整体 QPS {total / wall:.1f}")
    print("=" * 68)
    print(f"{'接口':<10}{'请求':>7}{'错误':>6}{'QPS':>8}{'P50':>9}{'P95':>9}{'P99':>9}{'最大':>9}")
    for name, _, _, _, _ in TARGETS:
        vals = records.get(name, [])
        err = errors.get(name, 0)
        if not vals:
            continue
        print(f"{name:<10}{len(vals):>7}{err:>6}{len(vals) / wall:>8.1f}"
              f"{pct(vals, 0.5):>9.0f}{pct(vals, 0.95):>9.0f}{pct(vals, 0.99):>9.0f}{max(vals):>9.0f}")
    err_total = sum(errors.values())
    print("-" * 68)
    print(f"错误总数 {err_total}，错误率 {err_total / total:.2%}" if total else "没有采到样本")
    print(f"平均延迟 {statistics.mean([v for vals in records.values() for v in vals]):.0f} ms")
    return 0 if err_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
