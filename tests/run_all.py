"""一次跑完全部测试，给 CI 和给自己用

python tests/run_all.py            # 跑 7 套，全部用临时库副本
python tests/run_all.py --only smoke,hardening
python tests/run_all.py --eval     # 顺带跑评估集桩模式（80 条）
"""
import argparse
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUITES = [
    ("smoke", "tests/smoke_test.py"),
    ("permission", "tests/permission_test.py"),
    ("agent", "tests/agent_test.py"),
    ("phase3", "tests/phase3_test.py"),
    ("staff_agent", "tests/staff_agent_test.py"),
    ("langgraph", "tests/langgraph_test.py"),
    ("hardening", "tests/hardening_test.py"),
]


def run(script):
    env = dict(os.environ)
    env["PYTHONPATH"] = BASE_DIR
    env.setdefault("LAUNDRY_STAFF_INVITE_CODE", "laundry-2026")
    proc = subprocess.run([sys.executable, os.path.join(BASE_DIR, script)],
                          cwd=BASE_DIR, env=env, capture_output=True, text=True, encoding="utf-8")
    tail = [line for line in (proc.stdout or "").splitlines() if line.strip()][-1:]
    return proc.returncode, (tail[0] if tail else (proc.stderr or "").strip().splitlines()[-1:] or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="只跑指定套件，逗号分隔")
    parser.add_argument("--eval", action="store_true", help="再跑一遍评估集（桩模式）")
    args = parser.parse_args()

    wanted = [n.strip() for n in args.only.split(",") if n.strip()]
    failed = []
    for name, script in SUITES:
        if wanted and name not in wanted:
            continue
        code, tail = run(script)
        print(("PASS " if code == 0 else "FAIL ") + f"{name:<12}" + str(tail))
        if code != 0:
            failed.append(name)

    if args.eval:
        code, tail = run("scripts/eval_agent.py")
        print(("PASS " if code == 0 else "FAIL ") + f"{'eval':<12}" + str(tail))
        if code != 0:
            failed.append("eval")

    print()
    if failed:
        print("失败：" + "、".join(failed))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
