"""v2 升级迁移：订单五态 + 会员折扣字段

可重复执行（幂等）：
1. orders 表补充 original_amount / discount_rate / member_level_snapshot
2. 旧状态 pending -> ready（"待取衣"对应新的"可取衣"）
3. 历史订单折前金额回填为原总价、折扣率 1.0
"""
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "laundry.db")


def columns(cursor: sqlite3.Cursor, table: str) -> set[str]:
    cursor.execute("PRAGMA table_info(" + table + ")")
    return {row[1] for row in cursor.fetchall()}


def main() -> None:
    if not os.path.exists(DB_PATH):
        print("数据库不存在：" + DB_PATH)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    existing = columns(cur, "orders")
    for name, ddl in (
        ("original_amount", "REAL DEFAULT 0"),
        ("discount_rate", "REAL DEFAULT 1.0"),
        ("member_level_snapshot", "INTEGER DEFAULT 0"),
    ):
        if name not in existing:
            cur.execute("ALTER TABLE orders ADD COLUMN " + name + " " + ddl)
            print("新增字段：" + name)
        else:
            print("字段已存在：" + name)

    cur.execute("SELECT COUNT(*) FROM orders WHERE status='pending'")
    pending = cur.fetchone()[0]
    if pending:
        cur.execute("UPDATE orders SET status='ready' WHERE status='pending'")
        print("状态迁移 pending -> ready：" + str(pending) + " 条")

    cur.execute("SELECT COUNT(*) FROM orders WHERE original_amount IS NULL OR original_amount = 0")
    fill = cur.fetchone()[0]
    if fill:
        cur.execute("UPDATE orders SET original_amount = total_price WHERE original_amount IS NULL OR original_amount = 0")
        print("折前金额回填：" + str(fill) + " 条")

    cur.execute("SELECT COUNT(*) FROM orders WHERE discount_rate IS NULL")
    null_rate = cur.fetchone()[0]
    if null_rate:
        cur.execute("UPDATE orders SET discount_rate = 1.0 WHERE discount_rate IS NULL")

    conn.commit()

    cur.execute("SELECT status, COUNT(*) FROM orders GROUP BY status")
    print("状态分布：", cur.execute("SELECT status, COUNT(*) FROM orders GROUP BY status").fetchall())
    cur.execute("SELECT id, order_no, status, original_amount, discount_rate, total_price FROM orders ORDER BY id")
    for row in cur.fetchall():
        print("  ", row)
    conn.close()


if __name__ == "__main__":
    main()
