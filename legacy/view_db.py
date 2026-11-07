import sqlite3

conn = sqlite3.connect('laundry.db')
cursor = conn.cursor()

print("=== 数据库表结构 ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
for table in tables:
    table_name = table[0]
    print(f"\n--- {table_name} 表 ---")
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    print("列名:", [col[1] for col in columns])
    
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
    rows = cursor.fetchall()
    if rows:
        print("数据示例:")
        for row in rows:
            print(row)
    else:
        print("该表暂无数据")

conn.close()