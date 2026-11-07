#!/usr/bin/env python3
import http.server
import socketserver
import json
import urllib.parse
import os
from datetime import datetime
from database import *

class LaundryHandler(http.server.BaseHTTPRequestHandler):
    def send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_html_response(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'404 Not Found')

    def send_static_file(self, file_path, content_type):
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'404 Not Found')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # 页面路由
        if path == '/':
            self.send_html_response('templates/index.html')
        elif path == '/login':
            self.send_html_response('templates/login.html')
        elif path == '/receive':  # 收衣服
            self.send_html_response('templates/receive.html')
        elif path == '/pickup':   # 取衣服
            self.send_html_response('templates/pickup.html')
        elif path == '/members':  # 会员管理
            self.send_html_response('templates/members.html')
        
        # API路由
        elif path.startswith('/api/'):
            self.handle_api_get(path, params)
        
        # 静态文件
        elif path.startswith('/css/') or path.startswith('/js/'):
            if path.startswith('/css/'):
                file_path = 'static/css' + path[4:]
                self.send_static_file(file_path, 'text/css')
            elif path.startswith('/js/'):
                file_path = 'static/js' + path[3:]
                self.send_static_file(file_path, 'application/javascript')
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/'):
            try:
                content_length = int(self.headers['Content-Length'])
                body = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(body) if body else {}
                self.handle_api_post(path, data)
            except Exception as e:
                print(f"POST error: {e}", flush=True)
                self.send_json_response({'error': str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/'):
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}
            self.handle_api_put(path, data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/'):
            self.handle_api_delete(path)
        else:
            self.send_response(404)
            self.end_headers()

    def handle_api_get(self, path, params):
        # 登录
        if path == '/api/login':
            self.send_json_response({'error': 'Use POST method'}, 400)
        
        # 订单相关
        elif path == '/api/orders':
            status = params.get('status', [None])[0]
            keyword = params.get('keyword', [None])[0]
            
            if keyword:
                # 根据订单号、客户姓名、电话查询
                orders = fetch_all('''
                    SELECT o.*, c.name as customer_name, c.phone as customer_phone
                    FROM orders o
                    LEFT JOIN customers c ON o.customer_id = c.id
                    WHERE o.order_no LIKE ? OR c.name LIKE ? OR c.phone LIKE ?
                    ORDER BY o.receive_time DESC
                ''', (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
            elif status:
                orders = fetch_all('''
                    SELECT o.*, c.name as customer_name, c.phone as customer_phone
                    FROM orders o
                    LEFT JOIN customers c ON o.customer_id = c.id
                    WHERE o.status = ?
                    ORDER BY o.receive_time DESC
                ''', (status,))
            else:
                orders = fetch_all('''
                    SELECT o.*, c.name as customer_name, c.phone as customer_phone
                    FROM orders o
                    LEFT JOIN customers c ON o.customer_id = c.id
                    ORDER BY o.receive_time DESC
                ''')
            
            orders_list = []
            for order in orders:
                orders_list.append({
                    'id': order[0],
                    'order_no': order[1],
                    'customer_id': order[2],
                    'customer_name': order[11] if len(order) > 11 else '',
                    'customer_phone': order[12] if len(order) > 12 else '',
                    'items': order[3],
                    'total_price': order[4],
                    'deposit': order[5],
                    'status': order[6],
                    'receive_time': order[7],
                    'expected_pickup': order[8],
                    'actual_pickup': order[9]
                })
            self.send_json_response(orders_list)
        
        elif path == '/api/orders/pending':
            # 获取待取衣的订单
            orders = fetch_all('''
                SELECT o.*, c.name as customer_name, c.phone as customer_phone
                FROM orders o
                LEFT JOIN customers c ON o.customer_id = c.id
                WHERE o.status = 'pending'
                ORDER BY o.receive_time DESC
            ''')
            orders_list = []
            for order in orders:
                orders_list.append({
                    'id': order[0],
                    'order_no': order[1],
                    'customer_id': order[2],
                    'customer_name': order[11] if len(order) > 11 else '',
                    'customer_phone': order[12] if len(order) > 12 else '',
                    'items': order[3],
                    'total_price': order[4],
                    'deposit': order[5],
                    'status': order[6],
                    'receive_time': order[7]
                })
            self.send_json_response(orders_list)
        
        elif path.startswith('/api/orders/'):
            order_id = int(path.split('/')[-1])
            order = get_order_by_id(order_id)
            if order:
                customer = get_customer_by_id(order[2]) if order[2] else None
                self.send_json_response({
                    'id': order[0],
                    'order_no': order[1],
                    'customer_id': order[2],
                    'customer_name': customer[1] if customer else '',
                    'customer_phone': customer[2] if customer else '',
                    'items': order[3],
                    'total_price': order[4],
                    'deposit': order[5],
                    'status': order[6],
                    'receive_time': order[7],
                    'expected_pickup': order[8],
                    'actual_pickup': order[9]
                })
            else:
                self.send_json_response({'error': '订单不存在'}, 404)
        
        # 客户/会员相关
        elif path == '/api/customers' or path == '/api/members':
            keyword = params.get('keyword', [None])[0]
            if keyword:
                customers = search_customers(keyword)
            else:
                customers = get_all_customers()
            customers_list = []
            for customer in customers:
                customers_list.append({
                    'id': customer[0],
                    'name': customer[1],
                    'phone': customer[2],
                    'address': customer[3],
                    'member_level': customer[4],
                    'points': customer[5],
                    'created_at': customer[6],
                    'level_name': self.get_member_level_name(customer[4])
                })
            self.send_json_response(customers_list)
        
        elif path.startswith('/api/customers/') or path.startswith('/api/members/'):
            customer_id = int(path.split('/')[-1])
            customer = get_customer_by_id(customer_id)
            if customer:
                self.send_json_response({
                    'id': customer[0],
                    'name': customer[1],
                    'phone': customer[2],
                    'address': customer[3],
                    'member_level': customer[4],
                    'points': customer[5],
                    'created_at': customer[6],
                    'level_name': self.get_member_level_name(customer[4])
                })
            else:
                self.send_json_response({'error': '客户不存在'}, 404)
        
        # 衣服分类
        elif path == '/api/categories':
            categories = get_all_categories()
            categories_list = []
            for cat in categories:
                categories_list.append({
                    'id': cat[0],
                    'name': cat[1],
                    'description': cat[3]
                })
            self.send_json_response(categories_list)
        
        # 服务项目
        elif path == '/api/services':
            services = get_all_service_items()
            services_list = []
            for service in services:
                services_list.append({
                    'id': service[0],
                    'name': service[1],
                    'price': service[2],
                    'unit': service[3],
                    'category': service[4],
                    'description': service[5]
                })
            self.send_json_response(services_list)
        
        # 统计数据
        elif path == '/api/stats':
            today = datetime.now().strftime('%Y-%m-%d')
            today_orders = fetch_all('SELECT COUNT(*) FROM orders WHERE DATE(receive_time) = ?', (today,))
            pending_orders = fetch_all('SELECT COUNT(*) FROM orders WHERE status = "pending"')
            total_income = fetch_all('SELECT SUM(amount) FROM transactions WHERE type = "income"')
            total_customers = fetch_all('SELECT COUNT(*) FROM customers')
            
            self.send_json_response({
                'today_orders': today_orders[0][0] if today_orders else 0,
                'pending_orders': pending_orders[0][0] if pending_orders else 0,
                'total_income': total_income[0][0] if total_income and total_income[0][0] else 0,
                'total_customers': total_customers[0][0] if total_customers else 0
            })
        
        else:
            self.send_json_response({'error': 'API not found'}, 404)

    def handle_api_post(self, path, data):
        # 登录
        if path == '/api/login':
            username = data.get('username')
            password = data.get('password')
            user = get_user_by_username(username)
            if user and user[2] == password:
                self.send_json_response({
                    'id': user[0],
                    'username': user[1],
                    'role': user[3],
                    'name': user[4]
                })
            else:
                self.send_json_response({'error': '用户名或密码错误'}, 401)
        
        # 注册
        elif path == '/api/register':
            username = data.get('username')
            password = data.get('password')
            name = data.get('name')
            
            if not username or not password or not name:
                self.send_json_response({'error': '用户名、密码和姓名不能为空'}, 400)
                return
            
            if get_user_by_username(username):
                self.send_json_response({'error': '用户名已存在'}, 400)
                return
            
            user_id = create_user(username, password, name)
            if user_id:
                self.send_json_response({'message': '注册成功，请登录', 'user_id': user_id})
            else:
                self.send_json_response({'error': '注册失败'}, 500)
        
        # 新增订单（收衣服）
        elif path == '/api/orders':
            customer_name = data.get('customer_name')
            customer_phone = data.get('customer_phone')
            items = data.get('items')
            total_price = data.get('total_price', 0)
            deposit = data.get('deposit', 0)
            pay_now = data.get('pay_now', False)  # 是否现在支付
            
            # 查找或创建客户
            customer = get_customer_by_phone(customer_phone)
            if not customer:
                customer_id = add_customer(customer_name, customer_phone)
            else:
                customer_id = customer[0]
            
            # 生成订单号
            order_no = f'O{datetime.now().strftime("%Y%m%d%H%M%S")}'
            
            # 创建订单
            order_id = add_order(order_no, customer_id, items, total_price, deposit, 1)
            
            # 如果现在支付，记录交易
            if pay_now and deposit > 0:
                add_transaction(order_id, 'income', deposit, '收衣时支付定金', 1)
            
            # 记录日志
            add_log(1, 'create_order', order_no, f'创建订单，客户：{customer_name}')
            
            self.send_json_response({
                'id': order_id,
                'order_no': order_no,
                'message': '订单创建成功'
            })
        
        # 新增客户/会员
        elif path == '/api/customers' or path == '/api/members':
            name = data.get('name')
            phone = data.get('phone')
            address = data.get('address', '')
            member_level = data.get('member_level', 0)
            
            customer_id = add_customer(name, phone, address)
            if customer_id:
                if member_level > 0:
                    update_customer_member_level(customer_id, member_level)
                add_log(1, 'add_customer', name, f'新增会员，电话：{phone}')
                self.send_json_response({'id': customer_id, 'message': '添加成功'})
            else:
                self.send_json_response({'error': '该手机号已存在'}, 400)
        
        # 新增衣服分类
        elif path == '/api/categories':
            name = data.get('name')
            description = data.get('description', '')
            category_id = add_category(name, description)
            if category_id:
                self.send_json_response({'id': category_id, 'message': '添加成功'})
            else:
                self.send_json_response({'error': '该分类已存在'}, 400)
        
        # 新增服务项目
        elif path == '/api/services':
            name = data.get('name')
            price = data.get('price', 0)
            unit = data.get('unit', '件')
            category = data.get('category', '')
            description = data.get('description', '')
            service_id = add_service_item(name, price, unit, category, description)
            if service_id:
                self.send_json_response({'id': service_id, 'message': '添加成功'})
            else:
                self.send_json_response({'error': '该服务项目已存在'}, 400)
        
        else:
            self.send_json_response({'error': 'API not found'}, 404)

    def handle_api_put(self, path, data):
        # 修改订单
        if path.startswith('/api/orders/'):
            order_id = int(path.split('/')[-1])
            items = data.get('items')
            total_price = data.get('total_price')
            deposit = data.get('deposit')
            status = data.get('status')
            
            if status == 'completed':
                # 取衣结算
                order = get_order_by_id(order_id)
                if order:
                    # 计算剩余金额
                    remaining = order[4] - order[5]  # 总价 - 定金
                    if remaining > 0:
                        add_transaction(order_id, 'income', remaining, '取衣结算', 1)
                    update_order_status(order_id, 'completed', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    add_log(1, 'complete_order', order[1], '订单完成')
                    self.send_json_response({'message': '结算成功'})
                else:
                    self.send_json_response({'error': '订单不存在'}, 404)
            else:
                update_order(order_id, items, total_price, deposit)
                add_log(1, 'update_order', str(order_id), '修改订单')
                self.send_json_response({'message': '修改成功'})
        
        # 修改客户/会员
        elif path.startswith('/api/customers/') or path.startswith('/api/members/'):
            customer_id = int(path.split('/')[-1])
            name = data.get('name')
            phone = data.get('phone')
            address = data.get('address')
            member_level = data.get('member_level')
            points = data.get('points')
            
            update_customer(customer_id, name, phone, address)
            if member_level is not None:
                update_customer_member_level(customer_id, member_level)
            if points is not None:
                update_customer_points(customer_id, points)
            
            add_log(1, 'update_customer', name, '修改会员信息')
            self.send_json_response({'message': '修改成功'})
        
        else:
            self.send_json_response({'error': 'API not found'}, 404)

    def handle_api_delete(self, path):
        # 删除订单
        if path.startswith('/api/orders/'):
            order_id = int(path.split('/')[-1])
            order = get_order_by_id(order_id)
            if order:
                delete_order(order_id)
                add_log(1, 'delete_order', order[1], '删除订单')
                self.send_json_response({'message': '删除成功'})
            else:
                self.send_json_response({'error': '订单不存在'}, 404)
        
        # 删除客户/会员
        elif path.startswith('/api/customers/') or path.startswith('/api/members/'):
            customer_id = int(path.split('/')[-1])
            customer = get_customer_by_id(customer_id)
            if customer:
                delete_customer(customer_id)
                add_log(1, 'delete_customer', customer[1], '删除会员')
                self.send_json_response({'message': '删除成功'})
            else:
                self.send_json_response({'error': '客户不存在'}, 404)
        
        else:
            self.send_json_response({'error': 'API not found'}, 404)

    def get_member_level_name(self, level):
        levels = {
            0: '普通客户',
            1: '普通会员',
            2: '银卡会员',
            3: '金卡会员',
            4: '钻石会员'
        }
        return levels.get(level, '普通客户')

def run_server(port=8888):
    with socketserver.TCPServer(('127.0.0.1', port), LaundryHandler) as httpd:
        print(f'洗衣店管理系统运行在 http://127.0.0.1:{port}', flush=True)
        print('按 Ctrl+C 停止服务器', flush=True)
        httpd.serve_forever()

if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    run_server(port)
