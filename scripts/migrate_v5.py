"""v5 迁移：软删除 / 站内消息 / Agent 指标 / 耗材用量

对应 P0-5 与 P1：删除订单不再物理删行、消息与指标要落库、库存要和订单挂钩。
幂等：重复执行只会跳过已存在的列与表。
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import DB_PATH, INVENTORY_SUPPLY_NAME  # noqa: E402

ORDER_COLUMNS = [
    ("is_deleted", "INTEGER DEFAULT 0"),
]

NEW_TABLES = {
    "notifications": """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            type VARCHAR(32) DEFAULT 'info',
            title VARCHAR(100) DEFAULT '',
            body TEXT DEFAULT '',
            order_id INTEGER REFERENCES orders(id),
            is_read INTEGER DEFAULT 0,
            created_at VARCHAR(32)
        )
    """,
    "agent_metrics": """
        CREATE TABLE IF NOT EXISTS agent_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key VARCHAR(64) DEFAULT '',
            side VARCHAR(16) DEFAULT 'customer',
            engine VARCHAR(16) DEFAULT 'loop',
            question_chars INTEGER DEFAULT 0,
            answer_chars INTEGER DEFAULT 0,
            rounds INTEGER DEFAULT 0,
            tools_used VARCHAR(255) DEFAULT '',
            elapsed_ms INTEGER DEFAULT 0,
            ok INTEGER DEFAULT 1,
            created_at VARCHAR(32)
        )
    """,
    "inventory_usages": """
        CREATE TABLE IF NOT EXISTS inventory_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER REFERENCES orders(id),
            item_name VARCHAR(64) DEFAULT '',
            quantity INTEGER DEFAULT 0,
            pieces INTEGER DEFAULT 0,
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

        cur.execute("CREATE INDEX IF NOT EXISTS ix_notifications_customer ON notifications(customer_id, is_read)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_inventory_usages_order ON inventory_usages(order_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_agent_metrics_created ON agent_metrics(created_at)")

        # 耗材条目：不存在就建一条 0 库存的，便于管理端看见"要入库了"
        cur.execute("SELECT COUNT(*) FROM inventory WHERE name = ?", (INVENTORY_SUPPLY_NAME,))
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO inventory (name, quantity, unit, price, created_at) VALUES (?, 0, '件', 0, datetime('now','localtime'))",
                (INVENTORY_SUPPLY_NAME,),
            )
            print(f"[+] 库存条目「{INVENTORY_SUPPLY_NAME}」已创建（数量 0，请在管理端入库）")
        else:
            print(f"[=] 库存条目「{INVENTORY_SUPPLY_NAME}」已存在")

        conn.commit()

        print("[*] orders 列：" + ", ".join(table_columns(cur, "orders")))
        cur.execute("SELECT COUNT(*) FROM orders")
        print(f"[*] 订单总数 {cur.fetchone()[0]}")
        for table in NEW_TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"[*] {table} {cur.fetchone()[0]} 行")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
