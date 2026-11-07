# -*- coding: utf-8 -*-
"""v6 迁移：给 agent_metrics 增加 question 字段（幂等）"""
import os, shutil, sqlite3, sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "laundry.db")
BACKUP = os.path.join(BASE, "laundry_backup_v6_" + datetime.now().strftime("%Y%m%d_%H%M") + ".db")
shutil.copy(DB, BACKUP)
print("备份：" + BACKUP)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cols = [r[1] for r in cur.execute("PRAGMA table_info(agent_metrics)").fetchall()]
if "question" in cols:
    print("question 已存在，跳过")
else:
    cur.execute("ALTER TABLE agent_metrics ADD COLUMN question VARCHAR DEFAULT ''")
    print("已新增 agent_metrics.question")
conn.commit()
cols = [r[1] for r in cur.execute("PRAGMA table_info(agent_metrics)").fetchall()]
print("agent_metrics 列：" + ", ".join(cols))
print("行数：" + str(cur.execute("SELECT COUNT(*) FROM agent_metrics").fetchone()[0]))
conn.close()
