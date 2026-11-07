/* 财务报表 */
document.addEventListener('DOMContentLoaded', function () {
    initShell('finance');
    const today = new Date();
    const iso = today.toISOString().slice(0, 10);
    $('dailyDate').value = iso;
    $('rangeStart').value = iso.slice(0, 8) + '01';
    $('rangeEnd').value = iso;
    loadDaily();
    loadRange();
    loadRanking();
    loadTransactions();
});

async function loadDaily() {
    const date = $('dailyDate').value;
    const res = await api.get('/api/stats/daily?date=' + date);
    if (!res.ok) { toast(res.error, 'error'); return; }
    const d = res.data;
    $('dOrders').textContent = d.order_count;
    $('dCompleted').textContent = d.completed_count;
    $('dReceived').textContent = money(d.total_received);
    $('dIncome').textContent = money(d.total_income);
    $('dExpense').textContent = money(d.total_expense);
    $('dNet').textContent = money(d.net_profit);
}

async function loadRange() {
    const start = $('rangeStart').value;
    const end = $('rangeEnd').value;
    if (!start || !end) { toast('请选择开始与结束日期', 'warn'); return; }
    const res = await api.get('/api/stats/range?start_date=' + start + '&end_date=' + end);
    if (!res.ok) { toast(res.error, 'error'); return; }
    const r = res.data;
    $('rOrders').textContent = r.order_count;
    $('rTotal').textContent = money(r.order_total_price);
    $('rIncome').textContent = money(r.total_income);
    $('rExpense').textContent = money(r.total_expense);
    $('rAvg').textContent = money(r.avg_order_value);
    $('rNet').textContent = money(r.net_profit);
}

async function loadRanking() {
    const res = await api.get('/api/stats/services?limit=10');
    const body = $('rankBody');
    if (!res.ok) { body.innerHTML = '<tr><td colspan="3" class="empty">加载失败</td></tr>'; return; }
    const rows = res.data || [];
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="3" class="empty">暂无洗衣明细</td></tr>';
        return;
    }
    body.innerHTML = rows.map(function (r) {
        return '<tr><td class="strong">' + escapeHtml(r.service_name) + '</td>' +
            '<td class="mono">' + r.quantity + ' 件</td>' +
            '<td class="mono">' + money(r.amount) + '</td></tr>';
    }).join('');
}

async function loadTransactions() {
    const res = await api.get('/api/transactions?limit=20');
    const body = $('txBody');
    if (!res.ok) { body.innerHTML = '<tr><td colspan="4" class="empty">加载失败</td></tr>'; return; }
    const rows = res.data || [];
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="4" class="empty">暂无流水</td></tr>';
        return;
    }
    body.innerHTML = rows.map(function (t) {
        const isIncome = t.type === 'income';
        return '<tr>' +
            '<td class="muted">' + fmtDate(t.transaction_time) + '</td>' +
            '<td><span class="badge ' + (isIncome ? 'badge-completed' : 'badge-danger') + '">' + (isIncome ? '收入' : '支出') + '</span></td>' +
            '<td class="mono strong">' + (isIncome ? '+' : '-') + money(t.amount) + '</td>' +
            '<td class="muted">' + escapeHtml(t.description || '-') + '</td>' +
            '</tr>';
    }).join('');
}

function openTx(type) {
    $('txType').value = type;
    $('txTitle').textContent = type === 'income' ? '登记收入' : '登记支出';
    $('txAmount').value = '';
    $('txDesc').value = '';
    openModal('txModal');
}

async function submitTx() {
    const amount = parseFloat($('txAmount').value || '0');
    if (!(amount > 0)) { toast('金额必须大于 0', 'warn'); return; }
    const res = await api.post('/api/transactions', {
        type: $('txType').value,
        amount: amount,
        description: $('txDesc').value.trim()
    });
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('已登记', 'success');
    closeModal('txModal');
    loadDaily();
    loadRange();
    loadTransactions();
}
