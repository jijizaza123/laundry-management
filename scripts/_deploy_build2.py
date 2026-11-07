# -*- coding: utf-8 -*-
"""去掉失效的镜像加速，直接拉基础镜像；成功再构建"""
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
        if len(buf) > 300:
            buf = buf[-300:]
    print(f"===== {label} ({time.time()-t0:.0f}s) =====")
    print("\n".join(buf)[-2500:])


run("rm -f /etc/docker/daemon.json; systemctl restart docker; sleep 2; docker info | grep -i 'registry mirrors' || echo no-mirror", 120, "清理镜像配置")
run("docker pull python:3.13-slim 2>&1 | tail -6", 900, "拉基础镜像")
run(f"cd {REMOTE} && docker compose build 2>&1 | tail -30", 1800, "构建镜像")
client.close()
print("done")
