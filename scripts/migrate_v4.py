"""v4 迁移：订单来源 / 上门取件预约 / 到店复核 / 会话存储

幂等：重复执行只会跳过已存在的列与表。
SQLite 的 ALTER TABLE 只支持 ADD COLUMN，且不能带 UNIQUE，所以唯一约束一律走 CREATE INDEX。
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import DB_PATH  # noqa: E402

ORDER_COLUMNS = [
    ("source", "TEXT DEFAULT 'staff'"),
    ("appointment_id", "INTEGER"),
    ("review_status", "TEXT DEFAULT 'confirmed'"),
]

NEW_TABLES = {
    "appointments": """
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appt_no VARCHAR(64) NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            expected_time VARCHAR(32) NOT NULL,
            address VARCHAR(255) NOT NULL,
            note TEXT DEFAULT '',
            status VARCHAR(32) DEFAULT 'pending',
            staff_id INTEGER REFERENCES users(id),
            created_at VARCHAR(32)
        )
    """,
    "order_amount_logs": """
        CREATE TABLE IF NOT EXISTS order_amount_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            old_total FLOAT DEFAULT 0,
            new_total FLOAT DEFAULT 0,
            reason TEXT DEFAULT '',
            staff_id INTEGER REFERENCES users(id),
            customer_confirmed INTEGER DEFAULT 0,
            created_at VARCHAR(32)
        )
    """,
    "chat_messages": """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key VARCHAR(64) NOT NULL,
            role VARCHAR(16) NOT NULL,
            content TEXT DEFAULT '',
            tools_used VARCHAR(255) DEFAULT '',
            created_at VARCHAR(32)
        )
    """,
}


def table_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    try:
        existing = table_columns(cur, "orders")
        for name, spec in ORDER_COLUMNS:
            if name in existing:
                print(f"[=] orders.{name} 已存在，跳过")
                continue
            cur.execute(f"ALTER TABLE orders ADD COLUMN {name} {spec}")
            print(f"[+] orders.{name} 已添加")

        for table, ddl in NEW_TABLES.items():
            cur.execute(ddl)
            print(f"[+] 表 {table} 就绪")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_key ON chat_messages(session_key)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_appointments_customer ON appointments(customer_id)")
        conn.commit()

        # 回读校验
        print("[*] orders 列：" + ", ".join(table_columns(cur, "orders")))
        cur.execute("SELECT COUNT(*) FROM orders")
        print(f"[*] 订单总数 {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*) FROM orders WHERE source = 'online'")
        print(f"[*] 客户端线上下单 {cur.fetchone()[0]} 单")
        cur.execute("SELECT COUNT(*) FROM orders WHERE review_status != 'confirmed'")
        print(f"[*] 待复核/待确认 {cur.fetchone()[0]} 单")
        for table in NEW_TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"[*] {table} {cur.fetchone()[0]} 行")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
