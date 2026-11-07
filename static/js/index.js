/* 首页看板 */
document.addEventListener('DOMContentLoaded', async function () {
    initShell('dashboard');
    await Promise.all([loadStats(), loadTrend(), loadOverdue(), loadRecent()]);
});

async function loadStats() {
    const res = await api.get('/api/stats');
    if (!res.ok) { toast(res.error, 'error'); return; }
    const s = res.data;

    $('sTodayOrders').textContent = s.today_orders;
    $('sInStore').textContent = s.in_store;
    $('sInStoreHint').textContent = '待洗涤 ' + s.received_count + ' · 洗涤中 ' + s.washing_count + ' · 可取衣 ' + s.ready_count;
    $('sReady').textContent = s.ready_count;
    $('sOverdue').textContent = s.overdue_count;

    $('todayLabel').textContent = s.date + ' 经营数据';
    $('fTodayIncome').textContent = money(s.today_income);
    $('fTotalIncome').textContent = money(s.total_income);
    $('fTotalExpense').textContent = money(s.total_expense);
    $('fNetProfit').textContent = money(s.net_profit);
    $('fCustomers').textContent = s.total_customers;
}

async function loadTrend() {
    const res = await api.get('/api/stats/trend?days=7');
    if (!res.ok) return;
    const rows = res.data || [];
    const totalOrders = rows.reduce((s, r) => s + Number(r.order_count || 0), 0);

    if (!totalOrders) {
        $('trendChart').innerHTML = '<div class="chart-empty">近 7 日暂无收衣记录</div>';
        return;
    }

    const maxOrders = Math.max(1, ...rows.map(r => r.order_count));
    const maxIncome = Math.max(1, ...rows.map(r => r.income));

    $('trendChart').innerHTML = rows.map(function (r) {
        const h1 = r.order_count ? Math.max(6, Math.round((r.order_count / maxOrders) * 118)) : 0;
        const h2 = r.income ? Math.max(6, Math.round((r.income / maxIncome) * 118)) : 0;
        return '<div class="col" title="' + r.date + ' 订单 ' + r.order_count + ' 单 / 收入 ' + money(r.income) + '">' +
            '<div class="bar-wrap">' +
            '<div class="bar" style="height:' + h1 + 'px"></div>' +
            '<div class="bar b2" style="height:' + h2 + 'px"></div>' +
            '</div><div class="x">' + r.label + '</div></div>';
    }).join('');
}

async function loadOverdue() {
    const res = await api.get('/api/orders/overdue');
    const body = $('overdueBody');
    if (!res.ok) { body.innerHTML = '<tr><td colspan="4" class="empty">加载失败</td></tr>'; return; }
    const rows = res.data.orders || [];
    $('overdueSub').textContent = rows.length ? ('共 ' + rows.length + ' 单待跟进') : '暂无逾期';
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="4" class="empty">没有逾期未取的订单</td></tr>';
        return;
    }
    body.innerHTML = rows.slice(0, 8).map(function (o) {
        return '<tr>' +
            '<td class="mono">' + escapeHtml(o.order_no) + '</td>' +
            '<td>' + escapeHtml(o.customer_name) + '</td>' +
            '<td class="mono">' + money(o.remaining) + '</td>' +
            '<td><span class="badge badge-danger">' + fmtDate(o.expected_pickup) + '</span></td>' +
            '</tr>';
    }).join('');
}

async function loadRecent() {
    const res = await api.get('/api/orders?limit=8');
    const body = $('recentBody');
    if (!res.ok) { body.innerHTML = '<tr><td colspan="4" class="empty">加载失败</td></tr>'; return; }
    const rows = res.data || [];
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="4" class="empty">还没有订单</td></tr>';
        return;
    }
    body.innerHTML = rows.map(function (o) {
        return '<tr>' +
            '<td class="mono">' + escapeHtml(o.order_no) + '</td>' +
            '<td>' + escapeHtml(o.customer_name) + '</td>' +
            '<td>' + statusBadge(o.status) + '</td>' +
            '<td class="mono">' + money(o.total_price) + '</td>' +
            '</tr>';
    }).join('');
}
