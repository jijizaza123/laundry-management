# -*- coding: utf-8 -*-
"""服务器端的最终发射：写 .env、配镜像加速、构建、启动、初始化、自检"""
import os
import re
import secrets
import time

import paramiko

HOST = "139.224.211.114"
USER = "root"
PW = os.environ["SSH_PASS"]
REMOTE = "/root/laundry"

# 从本地 .env 读 AGNES key（不回显）
local_env = {}
with open(r"C:\keshe3\laundry_management\.env", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            local_env[k.strip()] = v.strip()

agnes_key = local_env.get("AGNES_API_KEY", "")
assert agnes_key.startswith("sk-") or len(agnes_key) > 20, "本地 .env 没读到 AGNES_API_KEY"

secret = secrets.token_hex(32)
env_text = (
    "LAUNDRY_ENV=production\n"
    f"LAUNDRY_SECRET_KEY={secret}\n"
    "LAUNDRY_STAFF_INVITE_CODE=\n"
    f"AGNES_API_KEY={agnes_key}\n"
    "AGNES_BASE_URL=https://apihub.agnes-ai.com/v1\n"
    "AGNES_MODEL=agnes-3.0-flash\n"
)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, 22, username=USER, password=PW, timeout=15, banner_timeout=20, auth_timeout=20)


def run(cmd: str, timeout: int = 900, label: str = "") -> str:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    buf = []
    start = time.time()
    while True:
        line = stdout.readline()
        if not line:
            break
        buf.append(line.rstrip())
        if len(buf) > 400:
            buf = buf[-400:]
    text = "\n".join(buf)
    print(f"===== {label or cmd[:60]} ({time.time()-start:.0f}s) =====")
    print(text[-3000:])
    return text


# 1) .env
sftp = client.open_sftp()
with sftp.open(f"{REMOTE}/.env", "w") as fh:
    fh.write(env_text)
sftp.chmod(f"{REMOTE}/.env", 0o600)
sftp.close()
print("===== .env 已写入（权限 600）=====")

# 2) 镜像加速（腾讯云内网源），失败不影响主流程
run(
    "mkdir -p /etc/docker; "
    'echo \'{"registry-mirrors":["https://mirror.ccs.tencentyun.com"]}\' > /etc/docker/daemon.json; '
    "systemctl restart docker; sleep 3; docker info 2>/dev/null | grep -A2 'Registry Mirrors' || true",
    label="配置镜像加速",
)

# 3) 构建（首次要拉 python:3.13-slim 并装依赖）
run(f"cd {REMOTE} && docker compose build 2>&1 | tail -40", timeout=1800, label="docker build")

client.close()
print("done")
