import sqlite3
import os

DB_PATH = 'laundry.db'

def init_db():
    if os.path.exists(DB_PATH):
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA encoding = "UTF-8"')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            address TEXT,
            member_level INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            customer_id INTEGER,
            items TEXT NOT NULL,
            total_price REAL NOT NULL,
            deposit REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            receive_time TEXT DEFAULT CURRENT_TIMESTAMP,
            expected_pickup TEXT,
            actual_pickup TEXT,
            staff_id INTEGER,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (staff_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            transaction_time TEXT DEFAULT CURRENT_TIMESTAMP,
            staff_id INTEGER,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (staff_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER DEFAULT 0,
            unit TEXT,
            price REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER,
            action TEXT NOT NULL,
            target TEXT,
            detail TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (staff_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE service_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            unit TEXT DEFAULT '件',
            category TEXT,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            parent_id INTEGER DEFAULT 0,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("INSERT INTO users (username, password, role, name) VALUES ('admin', 'admin123', 'admin', '管理员')")
    cursor.execute("INSERT INTO users (username, password, role, name) VALUES ('staff', 'staff123', 'staff', '员工')")
    
    cursor.execute("INSERT INTO service_items (name, price, unit, category, description) VALUES ('普通洗', 20, '件', '水洗', '普通衣物水洗')")
    cursor.execute("INSERT INTO service_items (name, price, unit, category, description) VALUES ('干洗', 35, '件', '干洗', '干洗服务')")
    cursor.execute("INSERT INTO service_items (name, price, unit, category, description) VALUES ('熨烫', 10, '件', '熨烫', '衣物熨烫')")
    cursor.execute("INSERT INTO service_items (name, price, unit, category, description) VALUES ('消毒', 15, '件', '消毒', '高温消毒')")
    cursor.execute("INSERT INTO service_items (name, price, unit, category, description) VALUES ('精洗', 50, '件', '水洗', '精细衣物清洗')")
    
    cursor.execute("INSERT INTO categories (name, description) VALUES ('上衣', '各类上衣')")
    cursor.execute("INSERT INTO categories (name, description) VALUES ('裤子', '各类裤子')")
    cursor.execute("INSERT INTO categories (name, description) VALUES ('外套', '各类外套')")
    cursor.execute("INSERT INTO categories (name, description) VALUES ('内衣', '各类内衣')")
    cursor.execute("INSERT INTO categories (name, description) VALUES ('家纺', '床上用品')")
    
    conn.commit()
    conn.close()

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA encoding = "UTF-8"')
    return conn

def execute_query(query, params=()):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id

def fetch_one(query, params=()):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    return result

def fetch_all(query, params=()):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results

def get_user_by_username(username):
    return fetch_one('SELECT * FROM users WHERE username = ?', (username,))

def create_user(username, password, name, role='staff'):
    return execute_query(
        'INSERT INTO users (username, password, name, role) VALUES (?, ?, ?, ?)',
        (username, password, name, role)
    )

def add_order(order_no, customer_id, items, total_price, deposit, staff_id):
    return execute_query(
        'INSERT INTO orders (order_no, customer_id, items, total_price, deposit, staff_id) VALUES (?, ?, ?, ?, ?, ?)',
        (order_no, customer_id, items, total_price, deposit, staff_id)
    )

def update_order_status(order_id, status, actual_pickup=None):
    if actual_pickup:
        execute_query(
            'UPDATE orders SET status = ?, actual_pickup = ? WHERE id = ?',
            (status, actual_pickup, order_id)
        )
    else:
        execute_query('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))

def update_order(order_id, items, total_price, deposit):
    execute_query(
        'UPDATE orders SET items = ?, total_price = ?, deposit = ? WHERE id = ?',
        (items, total_price, deposit, order_id)
    )

def delete_order(order_id):
    execute_query('DELETE FROM orders WHERE id = ?', (order_id,))

def get_orders(filter_status=None):
    if filter_status:
        return fetch_all('SELECT * FROM orders WHERE status = ? ORDER BY receive_time DESC', (filter_status,))
    return fetch_all('SELECT * FROM orders ORDER BY receive_time DESC')

def get_order_by_id(order_id):
    return fetch_one('SELECT * FROM orders WHERE id = ?', (order_id,))

def add_transaction(order_id, type_, amount, description, staff_id):
    return execute_query(
        'INSERT INTO transactions (order_id, type, amount, description, staff_id) VALUES (?, ?, ?, ?, ?)',
        (order_id, type_, amount, description, staff_id)
    )

def add_customer(name, phone, address=''):
    try:
        return execute_query(
            'INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)',
            (name, phone, address)
        )
    except sqlite3.IntegrityError:
        return None

def get_customer_by_phone(phone):
    return fetch_one('SELECT * FROM customers WHERE phone = ?', (phone,))

def get_customer_by_id(customer_id):
    return fetch_one('SELECT * FROM customers WHERE id = ?', (customer_id,))

def get_all_customers():
    return fetch_all('SELECT * FROM customers ORDER BY created_at DESC')

def search_customers(keyword):
    return fetch_all(
        'SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY created_at DESC',
        (f'%{keyword}%', f'%{keyword}%')
    )

def update_customer(customer_id, name, phone, address):
    execute_query(
        'UPDATE customers SET name = ?, phone = ?, address = ? WHERE id = ?',
        (name, phone, address, customer_id)
    )

def update_customer_points(customer_id, points):
    execute_query('UPDATE customers SET points = points + ? WHERE id = ?', (points, customer_id))

def update_customer_member_level(customer_id, level):
    execute_query('UPDATE customers SET member_level = ? WHERE id = ?', (level, customer_id))

def delete_customer(customer_id):
    execute_query('DELETE FROM customers WHERE id = ?', (customer_id,))

def add_log(staff_id, action, target, detail=''):
    execute_query(
        'INSERT INTO logs (staff_id, action, target, detail) VALUES (?, ?, ?, ?)',
        (staff_id, action, target, detail)
    )

def get_logs():
    return fetch_all('SELECT * FROM logs ORDER BY created_at DESC LIMIT 100')

def get_daily_summary(date):
    orders = fetch_all('SELECT * FROM orders WHERE DATE(receive_time) = ?', (date,))
    transactions = fetch_all('SELECT * FROM transactions WHERE DATE(transaction_time) = ?', (date,))
    
    total_received = sum(o[4] for o in orders) if orders else 0
    total_income = sum(t[3] for t in transactions if t[2] == 'income') if transactions else 0
    total_expense = sum(t[3] for t in transactions if t[2] == 'expense') if transactions else 0
    
    return {
        'date': date,
        'order_count': len(orders),
        'total_received': total_received,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_profit': total_income - total_expense
    }

def get_all_service_items():
    return fetch_all('SELECT * FROM service_items ORDER BY category, name')

def get_service_item_by_id(item_id):
    return fetch_one('SELECT * FROM service_items WHERE id = ?', (item_id,))

def add_service_item(name, price, unit='件', category='', description=''):
    try:
        return execute_query(
            'INSERT INTO service_items (name, price, unit, category, description) VALUES (?, ?, ?, ?, ?)',
            (name, price, unit, category, description)
        )
    except sqlite3.IntegrityError:
        return None

def update_service_item(item_id, name, price, unit, category, description):
    execute_query(
        'UPDATE service_items SET name = ?, price = ?, unit = ?, category = ?, description = ? WHERE id = ?',
        (name, price, unit, category, description, item_id)
    )

def delete_service_item(item_id):
    execute_query('DELETE FROM service_items WHERE id = ?', (item_id,))

def get_all_categories():
    return fetch_all('SELECT * FROM categories ORDER BY name')

def get_category_by_id(category_id):
    return fetch_one('SELECT * FROM categories WHERE id = ?', (category_id,))

def add_category(name, description=''):
    try:
        return execute_query(
            'INSERT INTO categories (name, description) VALUES (?, ?)',
            (name, description)
        )
    except sqlite3.IntegrityError:
        return None

def update_category(category_id, name, description):
    execute_query(
        'UPDATE categories SET name = ?, description = ? WHERE id = ?',
        (name, description, category_id)
    )

def delete_category(category_id):
    execute_query('DELETE FROM categories WHERE id = ?', (category_id,))

def get_transactions_by_date(date):
    return fetch_all('SELECT * FROM transactions WHERE DATE(transaction_time) = ? ORDER BY transaction_time DESC', (date,))

init_db()