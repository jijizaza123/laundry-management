/* 订单管理 */
var currentStatus = '';
var ORDERS = [];

document.addEventListener('DOMContentLoaded', function () {
    initShell('orders');
    document.querySelectorAll('#statusSeg button').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#statusSeg button').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            currentStatus = btn.dataset.status;
            loadOrders();
        });
    });
    loadOrders();
});

async function loadOrders() {
    const keyword = $('keyword').value.trim();
    let url = '/api/orders?limit=300';
    if (currentStatus) url += '&status=' + currentStatus;
    if (keyword) url += '&keyword=' + encodeURIComponent(keyword);

    const res = await api.get(url);
    const body = $('orderBody');
    if (!res.ok) {
        body.innerHTML = '<tr><td colspan="8" class="empty">' + escapeHtml(res.error) + '</td></tr>';
        return;
    }
    ORDERS = res.data || [];
    $('countLabel').textContent = '共 ' + ORDERS.length + ' 单';

    if (!ORDERS.length) {
        body.innerHTML = '<tr><td colspan="8" class="empty">没有符合条件的订单</td></tr>';
        return;
    }

    body.innerHTML = ORDERS.map(function (o) {
        const meta = STATUS_META[o.status] || {};
        const items = (o.items || '').split('\n')[0] || '-';
        const more = (o.items || '').split('\n').length > 1 ? ' …' : '';
        let actions = '';
        if (meta.next) {
            actions += '<button class="btn btn-ghost btn-sm" onclick="advance(' + o.id + ',\'' + meta.next + '\')">' + meta.nextText + '</button>';
        }
        if (o.status === 'ready' || o.status === 'washing' || o.status === 'received') {
            actions += '<button class="btn btn-success btn-sm" onclick="settle(' + o.id + ')">取衣结算</button>';
        }
        actions += '<button class="btn btn-ghost btn-sm" onclick="showReceipt(' + o.id + ')">单据</button>';
        if (o.status !== 'completed' && o.status !== 'cancelled') {
            actions += '<button class="btn btn-danger btn-sm" onclick="cancelOrder(' + o.id + ')">取消</button>';
        }

        return '<tr>' +
            '<td class="mono">' + escapeHtml(o.order_no) + (o.overdue ? ' <span class="badge badge-danger">逾期</span>' : '') + '</td>' +
            '<td>' + escapeHtml(o.customer_name) + '<div class="muted" style="font-size:11.5px;">' + escapeHtml(o.customer_phone) + '</div></td>' +
            '<td style="max-width:220px;">' + escapeHtml(items) + more + '<div class="muted" style="font-size:11.5px;">' + o.item_count + ' 件</div></td>' +
            '<td class="mono">' + money(o.total_price) +
            (o.discount_amount > 0 ? '<div class="muted" style="font-size:11px;">原 ' + num(o.original_amount) + '</div>' : '') + '</td>' +
            '<td class="mono">' + money(o.remaining) + '</td>' +
            '<td>' + statusBadge(o.status) + '</td>' +
            '<td class="muted">' + fmtDate(o.receive_time) + '</td>' +
            '<td><div class="actions">' + actions + '</div></td>' +
            '</tr>';
    }).join('');
}

async function advance(id, target) {
    const res = await api.post('/api/orders/' + id + '/status', { status: target });
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('状态已更新为 ' + res.data.status_text, 'success');
    loadOrders();
}

async function settle(id) {
    const order = ORDERS.find(function (o) { return o.id === id; });
    if (!order) return;
    if (!confirm('确认结算？客户待收金额 ' + money(order.remaining))) return;
    const res = await api.post('/api/orders/' + id + '/complete', {});
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('结算完成，实收 ' + money(res.data.settled_amount) + '，积分 +' + (res.data.points ? res.data.points.points_gained : 0), 'success');
    loadOrders();
}

async function cancelOrder(id) {
    if (!confirm('确认取消该订单？取消后不能恢复')) return;
    const res = await api.post('/api/orders/' + id + '/cancel', {});
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('订单已取消', 'success');
    loadOrders();
}

async function showReceipt(id) {
    const res = await api.get('/api/orders/' + id);
    if (!res.ok) { toast(res.error, 'error'); return; }
    $('receiptBody').innerHTML = renderReceipt(res.data);
    openModal('receiptModal');
}
