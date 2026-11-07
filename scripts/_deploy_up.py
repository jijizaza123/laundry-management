# -*- coding: utf-8 -*-
"""构建、启动、初始化数据、自检"""
import os
import time

import paramiko

HOST = "139.224.211.114"
PW = os.environ["SSH_PASS"]
REMOTE = "/root/laundry"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, 22, username="root", password=PW, timeout=15, banner_timeout=20, auth_timeout=20)


def run(cmd, timeout=1800, label=""):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    buf = []
    t0 = time.time()
    while True:
        line = stdout.readline()
        if not line:
            break
        buf.append(line.rstrip())
        if len(buf) > 400:
            buf = buf[-400:]
    text = "\n".join(buf)
    print(f"===== {label} ({time.time()-t0:.0f}s) =====\n{text[-2500:]}")
    return text


run(f"cd {REMOTE} && docker compose up -d --build 2>&1 | tail -25", 1800, "build + up")
run("sleep 8; cd %s && docker compose ps" % REMOTE, 120, "容器状态")
run("curl -s -o /dev/null -w 'health=%%{http_code}\\n' http://127.0.0.1:8000/api/health", 60, "本机健康检查")
out = run(f"cd {REMOTE} && docker compose exec -T app python scripts/seed_demo.py 2>&1 | tee /root/laundry/ADMIN_CREDENTIALS.txt", 300, "初始化数据")
run("curl -s -o /dev/null -w 'public=%%{http_code}\\n' http://139.224.211.114:8000/api/health", 60, "公网健康检查")
client.close()
print("done")
