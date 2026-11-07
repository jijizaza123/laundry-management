/* 取衣页：可取衣订单结算 */
var PICKUP_ORDERS = [];
var detailOrderId = null;

document.addEventListener('DOMContentLoaded', function () {
    initShell('pickup');
    document.getElementById('settleBtn').addEventListener('click', doSettle);
    loadOrders();
});

async function loadOrders() {
    const keyword = $('keyword').value.trim();
    let url = '/api/orders?status=ready&limit=300';
    if (keyword) url = '/api/orders?keyword=' + encodeURIComponent(keyword) + '&limit=300';

    const res = await api.get(url);
    const body = $('pickupBody');
    if (!res.ok) {
        body.innerHTML = '<tr><td colspan="8" class="empty">' + escapeHtml(res.error) + '</td></tr>';
        return;
    }
    let rows = res.data || [];
    if (keyword) {
        rows = rows.filter(function (o) { return o.status === 'ready' || o.status === 'washing' || o.status === 'received'; });
    }
    PICKUP_ORDERS = rows;
    $('countLabel').textContent = '共 ' + rows.length + ' 单';

    const overdue = rows.filter(function (o) { return o.overdue; }).length;
    $('pReady').textContent = rows.length;
    $('pOverdue').textContent = overdue;
    $('pRemaining').textContent = money(rows.reduce(function (sum, o) { return sum + Number(o.remaining || 0); }, 0));

    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="8" class="empty">暂无待取衣订单</td></tr>';
        return;
    }

    body.innerHTML = rows.map(function (o) {
        const lines = (o.items || '').split('\n');
        return '<tr>' +
            '<td class="mono">' + escapeHtml(o.order_no) + (o.overdue ? ' <span class="badge badge-danger">逾期</span>' : '') + '</td>' +
            '<td>' + escapeHtml(o.customer_name) + '<div class="muted" style="font-size:11.5px;">' + escapeHtml(o.customer_phone) + '</div></td>' +
            '<td style="max-width:210px;" class="muted">' + escapeHtml(lines[0] || '-') + (lines.length > 1 ? ' …' : '') + '</td>' +
            '<td class="mono">' + money(o.total_price) + '</td>' +
            '<td class="mono">' + money(o.paid_amount) + '</td>' +
            '<td class="mono strong">' + money(o.remaining) + '</td>' +
            '<td class="muted">' + (o.expected_pickup ? fmtDate(o.expected_pickup) : '未设置') + '</td>' +
            '<td><div class="actions">' +
            (o.status === 'ready'
                ? '<button class="btn btn-success btn-sm" onclick="openDetail(' + o.id + ')">取衣结算</button>'
                : '<button class="btn btn-ghost btn-sm" onclick="advanceReady(' + o.id + ')">先标记可取衣</button>') +
            '<button class="btn btn-ghost btn-sm" onclick="openDetail(' + o.id + ')">详情</button>' +
            '</div></td>' +
            '</tr>';
    }).join('');
}

async function advanceReady(id) {
    const res = await api.post('/api/orders/' + id + '/status', { status: 'ready' });
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('已标记为可取衣', 'success');
    loadOrders();
}

async function openDetail(id) {
    const res = await api.get('/api/orders/' + id);
    if (!res.ok) { toast(res.error, 'error'); return; }
    const o = res.data;
    detailOrderId = id;

    $('detailTitle').textContent = '订单 ' + o.order_no;
    const lines = (o.items_detail || []).map(function (i) {
        return '<div class="sline"><span>' + escapeHtml(i.category) + ' · ' + escapeHtml(i.service_name) +
            ' × ' + i.quantity + '</span><span class="mono">' + money(i.subtotal) + '</span></div>';
    }).join('') || '<div class="muted">无结构化明细</div>';

    $('detailBody').innerHTML =
        '<div class="sline"><span>客户</span><span>' + escapeHtml(o.customer_name) + '（' + escapeHtml(o.customer_phone) + '）</span></div>' +
        '<div class="sline"><span>状态</span><span>' + statusBadge(o.status) + '</span></div>' +
        '<div class="sline"><span>收衣时间</span><span class="mono">' + fmtDate(o.receive_time) + '</span></div>' +
        '<div class="sline"><span>预约取衣</span><span class="mono">' + (o.expected_pickup ? fmtDate(o.expected_pickup) : '未设置') + '</span></div>' +
        '<div class="dash" style="border-top:1px dashed var(--border);margin:10px 0;"></div>' + lines +
        '<div class="dash" style="border-top:1px dashed var(--border);margin:10px 0;"></div>' +
        '<div class="sline"><span>折前</span><span class="mono">' + money(o.original_amount) + '</span></div>' +
        '<div class="sline"><span>会员折扣</span><span class="mono">' + Math.round(Number(o.discount_rate) * 100) + '%</span></div>' +
        '<div class="sline"><span>应收</span><span class="mono">' + money(o.total_price) + '</span></div>' +
        '<div class="sline"><span>已收</span><span class="mono">' + money(o.paid_amount) + '</span></div>' +
        '<div class="sline total"><span>本次待收</span><span>' + money(o.remaining) + '</span></div>';

    const btn = $('settleBtn');
    btn.disabled = o.status !== 'ready';
    btn.textContent = o.status === 'ready' ? '确认结算' : '（订单还未到可取衣状态）';
    openModal('detailModal');
}

async function doSettle() {
    if (!detailOrderId) return;
    const res = await api.post('/api/orders/' + detailOrderId + '/complete', {});
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('结算完成，实收 ' + money(res.data.settled_amount), 'success');
    closeModal('detailModal');
    detailOrderId = null;
    loadOrders();
}
