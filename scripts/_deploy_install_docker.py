# -*- coding: utf-8 -*-
"""在云服务器上装 Docker（Ubuntu 24.04，apt 源）"""
import os
import time

import paramiko

HOST = "139.224.211.114"
USER = "root"
PW = os.environ["SSH_PASS"]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, 22, username=USER, password=PW, timeout=15, banner_timeout=20, auth_timeout=20)

CMD = (
    "set -x; export DEBIAN_FRONTEND=noninteractive; "
    "apt-get update -y >/tmp/apt.log 2>&1; "
    "apt-get install -y docker.io docker-compose-v2 >>/tmp/apt.log 2>&1; "
    "systemctl enable --now docker; "
    "docker --version; docker compose version || docker-compose version; "
    "tail -3 /tmp/apt.log"
)

stdin, stdout, stderr = client.exec_command(CMD, timeout=900, get_pty=True)
out = []
t0 = time.time()
while True:
    line = stdout.readline()
    if not line:
        break
    out.append(line.rstrip())
    if len(out) > 300:
        out = out[-300:]
print("\n".join(out))
print("elapsed=%.0fs" % (time.time() - t0))
client.close()
