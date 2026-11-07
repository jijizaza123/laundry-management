# -*- coding: utf-8 -*-
"""给 Docker 配国内可达的镜像加速，逐个试到能 pull 为止"""
import json
import os
import time

import paramiko

HOST = "139.224.211.114"
PW = os.environ["SSH_PASS"]

MIRRORS = [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com",
    "https://dockerproxy.net",
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, 22, username="root", password=PW, timeout=15, banner_timeout=20, auth_timeout=20)


def run(cmd, timeout=300, label=""):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    buf = []
    t0 = time.time()
    while True:
        line = stdout.readline()
        if not line:
            break
        buf.append(line.rstrip())
        if len(buf) > 200:
            buf = buf[-200:]
    text = "\n".join(buf)
    print(f"== {label} ({time.time()-t0:.0f}s) ==\n{text[-800:]}")
    return text


for m in MIRRORS:
    cfg = json.dumps({"registry-mirrors": [m]})
    run(f"printf '%s' '{cfg}' > /etc/docker/daemon.json && systemctl restart docker && sleep 2 && echo cfg-ok", 120, "写入 " + m)
    out = run("timeout 90 docker pull python:3.13-slim 2>&1 | tail -3", 180, "pull via " + m)
    if "i/o timeout" not in out and ("Status:" in out or "Downloaded" in out or "Pull complete" in out or "Already exists" in out):
        print("WORKS:", m)
        break
else:
    print("ALL FAILED")

client.close()
