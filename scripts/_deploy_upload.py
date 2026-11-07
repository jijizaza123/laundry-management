# -*- coding: utf-8 -*-
"""把项目上传到云服务器（SFTP，跳过密钥、数据库、缓存）"""
import os
import posixpath
import stat
import sys

import paramiko

HOST = "139.224.211.114"
USER = "root"
PW = os.environ["SSH_PASS"]
LOCAL = r"C:\keshe3\laundry_management"
REMOTE = "/root/laundry"

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".venv", "venv", "legacy"}
SKIP_FILES = {"laundry.db", ".env"}
SKIP_EXT = {".db", ".pyc", ".log", ".zip"}

transport = paramiko.Transport((HOST, 22))
transport.connect(username=USER, password=PW)
sftp = paramiko.SFTPClient.from_transport(transport)


def ensure_dir(path: str) -> None:
    parts = path.strip("/").split("/")
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except IOError:
            sftp.mkdir(cur)


ensure_dir(REMOTE)
count = 0
total = 0
for root, dirs, files in os.walk(LOCAL):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    rel = os.path.relpath(root, LOCAL).replace("\\", "/")
    remote_dir = REMOTE if rel == "." else posixpath.join(REMOTE, rel)
    ensure_dir(remote_dir)
    for name in files:
        if name in SKIP_FILES or os.path.splitext(name)[1].lower() in SKIP_EXT:
            continue
        local_path = os.path.join(root, name)
        size = os.path.getsize(local_path)
        remote_path = posixpath.join(remote_dir, name)
        sftp.put(local_path, remote_path)
        count += 1
        total += size

print(f"上传 {count} 个文件，{total/1024:.0f} KB")
sftp.close()
transport.close()
