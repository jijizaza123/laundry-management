"""v3 迁移：users 表增加 customer_id 列（客户账号绑定客户档案）

幂等，可重复执行。SQLite 的 ALTER TABLE 不支持加带 UNIQUE 的列，
因此先加普通列，再用 CREATE UNIQUE INDEX 补唯一约束（NULL 不参与唯一判定，
员工账号该列为空，不受影响）。

用法：
    python scripts/migrate_v3.py
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "laundry.db"


def column_names(cur: sqlite3.Cursor, table: str) -> list[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def main() -> int:
    if not DB_PATH.exists():
        print(f"[x] 数据库不存在：{DB_PATH}")
        return 1

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    changed = []

    try:
        cols = column_names(cur, "users")
        if "customer_id" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN customer_id INTEGER")
            changed.append("users.customer_id 列已添加")
        else:
            changed.append("users.customer_id 已存在，跳过")

        cur.execute("PRAGMA index_list(users)")
        indexes = [row[1] for row in cur.fetchall()]
        if "ux_users_customer_id" not in indexes:
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_customer_id ON users(customer_id)"
            )
            changed.append("唯一索引 ux_users_customer_id 已创建")
        else:
            changed.append("唯一索引已存在，跳过")

        conn.commit()

        # 校验：回读结构
        cols = column_names(cur, "users")
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE customer_id IS NOT NULL")
        bound = cur.fetchone()[0]
    finally:
        conn.close()

    for line in changed:
        print("[+] " + line)
    print(f"[i] users 表列：{', '.join(cols)}")
    print(f"[i] 账号总数 {user_count}，已绑定客户档案 {bound}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
