/* 我的订单：状态筛选 + 行内展开明细（不用弹窗，移动端也顺手） */
(function () {
    if (!meGuard()) return;

    let currentStatus = '';
    const body = document.getElementById('ordersBody');

    function closeAll() {
        body.querySelectorAll('tr.me-detail-row').forEach(function (tr) { tr.remove(); });
        body.querySelectorAll('button[data-id]').forEach(function (b) { b.textContent = '明细'; });
    }

    function render(rows) {
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="10" class="empty">没有符合条件的订单</td></tr>';
            return;
        }
        body.innerHTML = rows.map(function (o) {
            return '<tr>' +
                '<td class="mono">' + escapeHtml(o.order_no) + '</td>' +
                '<td>' + fmtDate(o.receive_time) + '</td>' +
                '<td>' + escapeHtml((o.items || '').split('\n')[0] || '-') + (o.items && o.items.indexOf('\n') > -1 ? ' …' : '') + '</td>' +
                '<td class="mono">' + (o.item_count || 0) + '</td>' +
                '<td class="mono">' + money(o.total_price) + '</td>' +
                '<td class="mono">' + money(o.paid_amount) + '</td>' +
                '<td class="mono">' + money(o.remaining) + '</td>' +
                '<td>' + statusBadge(o.status) +
                    (o.review_status && o.review_status !== 'confirmed'
                        ? ' <span class="badge badge-warn">' + escapeHtml(o.review_status === 'adjusted' ? '待你确认金额' : '待到店复核') + '</span>'
                        : '') +
                '</td>' +
                '<td>' + (fmtDate(o.expected_pickup) || '未预约') + '</td>' +
                '<td><button class="btn btn-ghost btn-sm" data-id="' + o.id + '">明细</button></td>' +
                '</tr>';
        }).join('');
        body.querySelectorAll('button[data-id]').forEach(function (btn) {
            btn.addEventListener('click', function () { toggleDetail(Number(btn.dataset.id), btn); });
        });
    }

    async function toggleDetail(id, btn) {
        const existing = btn.closest('tr').nextElementSibling;
        if (existing && existing.classList.contains('me-detail-row')) {
            existing.remove();
            btn.textContent = '明细';
            return;
        }
        closeAll();
        btn.textContent = '收起';
        const placeholder = document.createElement('tr');
        placeholder.className = 'me-detail-row';
        placeholder.innerHTML = '<td colspan="10"><div class="empty">加载中…</div></td>';
        btn.closest('tr').after(placeholder);

        const res = await api.get('/api/my/orders/' + id);
        if (!res.ok) {
            placeholder.innerHTML = '<td colspan="10" class="empty">' + escapeHtml(res.error || '查询失败') + '</td>';
            return;
        }
        const order = res.data.data;
        placeholder.innerHTML = '<td colspan="10"><div class="me-inline-detail">' + renderOrderDetail(order) + '</div></td>';
        const confirmBtn = placeholder.querySelector('button[data-confirm]');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', async function () {
                confirmBtn.disabled = true;
                confirmBtn.textContent = '确认中…';
                const r = await api.post('/api/my/orders/' + id + '/confirm-amount', {});
                if (r.ok) {
                    toast('已确认新金额', 'success');
                    placeholder.remove();
                    load();
                } else {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = '确认新金额';
                    toast(r.error || '确认失败', 'error');
                }
            });
        }
        placeholder.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    async function load() {
        body.innerHTML = '<tr><td colspan="10" class="empty">加载中…</td></tr>';
        const url = '/api/my/orders?limit=50' + (currentStatus ? '&status=' + encodeURIComponent(currentStatus) : '');
        const res = await api.get(url);
        if (!res.ok) {
            if (res.status !== 401) {
                body.innerHTML = '<tr><td colspan="10" class="empty">' + escapeHtml(res.error || '加载失败') + '</td></tr>';
            }
            return;
        }
        render(res.data.data || []);

        // 支持从首页跳过来直接展开某一单：/me/orders?order=12
        const wanted = Number((location.search.match(/order=(\d+)/) || [])[1]);
        if (wanted) {
            const btn = body.querySelector('button[data-id="' + wanted + '"]');
            if (btn) btn.click();
        }
    }

    document.querySelectorAll('#statusFilter button').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#statusFilter button').forEach(function (b) {
                b.classList.remove('active');
            });
            btn.classList.add('active');
            currentStatus = btn.dataset.status || '';
            load();
        });
    });

    load();
})();
