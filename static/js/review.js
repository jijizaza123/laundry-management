/* 到店复核：线上单核对件数后面料，金额有变留痕，等客户确认 */
(function () {
    if (!initShell('review')) return;
    const body = document.getElementById('reviewBody');

    function render(rows) {
        document.getElementById('pendingCount').textContent = String(rows.length);
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="7" class="empty">没有待复核的订单</td></tr>';
            return;
        }
        body.innerHTML = rows.map(function (o) {
            const canEdit = o.review_status === 'pending';
            return '<tr>' +
                '<td class="mono">' + escapeHtml(o.order_no) + '</td>' +
                '<td>' + escapeHtml(o.customer_name) + '<div class="muted mono">' + escapeHtml(o.customer_phone) + '</div></td>' +
                '<td>' + escapeHtml((o.items || '').split('\n').slice(0, 2).join(' / ')) + '</td>' +
                '<td class="mono">' + o.item_count + '</td>' +
                '<td class="mono">' + money(o.total_price) + '</td>' +
                '<td><span class="badge ' + (o.review_status === 'adjusted' ? 'badge-warn' : '') + '">' +
                escapeHtml(o.review_status_text) + '</span>' +
                (o.amount_logs && o.amount_logs.length
                    ? '<div class="muted">已调价 ' + money(o.amount_logs[0].new_total) + '，等客户确认</div>'
                    : '') + '</td>' +
                '<td>' + (canEdit
                    ? '<div class="review-actions">' +
                        '<input type="number" step="0.01" min="0.01" class="review-amount" placeholder="新金额" value="' + o.total_price + '">' +
                        '<input type="text" class="review-reason" placeholder="原因：实际 3 件 / 面料要精洗">' +
                        '<button class="btn btn-primary btn-sm" data-adjust="' + o.id + '">调价</button>' +
                        '<button class="btn btn-ghost btn-sm" data-approve="' + o.id + '">金额无误</button>' +
                      '</div>'
                    : '<span class="muted">等客户在手机上确认</span>') +
                '</td>' +
                '</tr>';
        }).join('');

        body.querySelectorAll('button[data-adjust]').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                const tr = btn.closest('tr');
                const amount = tr.querySelector('.review-amount').value;
                const reason = tr.querySelector('.review-reason').value;
                if (!reason.trim()) {
                    toast('调价必须写原因', 'error');
                    return;
                }
                btn.disabled = true;
                const res = await api.post('/api/orders/' + btn.dataset.adjust + '/adjust',
                    { new_total: Number(amount), reason: reason.trim() });
                btn.disabled = false;
                if (!res.ok) {
                    toast(res.error || '调价失败', 'error');
                    return;
                }
                toast('已调价，等客户确认', 'success');
                load();
            });
        });

        body.querySelectorAll('button[data-approve]').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                btn.disabled = true;
                const res = await api.post('/api/orders/' + btn.dataset.approve + '/approve', {});
                btn.disabled = false;
                if (!res.ok) {
                    toast(res.error || '操作失败', 'error');
                    return;
                }
                toast('复核通过', 'success');
                load();
            });
        });
    }

    async function load() {
        body.innerHTML = '<tr><td colspan="7" class="empty">加载中…</td></tr>';
        const res = await api.get('/api/orders/review-pending');
        if (!res.ok) {
            body.innerHTML = '<tr><td colspan="7" class="empty">' + escapeHtml(res.error || '加载失败') + '</td></tr>';
            return;
        }
        render(res.data.orders || []);
    }

    load();
})();
