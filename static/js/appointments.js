/* 上门取件：预约列表 + 确认 / 已取件 / 取消 */
(function () {
    if (!initShell('appointments')) return;
    const body = document.getElementById('apptBody');
    let currentStatus = '';

    const ACTIONS = {
        pending: [['confirmed', '确认预约', 'btn-primary'], ['cancelled', '取消', 'btn-ghost']],
        confirmed: [['completed', '已取件', 'btn-primary'], ['cancelled', '取消', 'btn-ghost']]
    };

    function render(rows) {
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="7" class="empty">没有预约记录</td></tr>';
            return;
        }
        body.innerHTML = rows.map(function (a) {
            const actions = ACTIONS[a.status] || [];
            return '<tr>' +
                '<td class="mono">' + escapeHtml(a.appt_no) + '</td>' +
                '<td>' + escapeHtml(a.customer_name) + '<div class="muted mono">' + escapeHtml(a.customer_phone) + '</div></td>' +
                '<td>' + escapeHtml(a.expected_time) + '</td>' +
                '<td>' + escapeHtml(a.address) + '</td>' +
                '<td>' + escapeHtml(a.note || '-') + '</td>' +
                '<td><span class="badge">' + escapeHtml(a.status_text) + '</span></td>' +
                '<td>' + actions.map(function (item) {
                    return '<button class="btn ' + item[2] + ' btn-sm" data-id="' + a.id + '" data-status="' +
                        item[0] + '">' + item[1] + '</button>';
                }).join(' ') + '</td>' +
                '</tr>';
        }).join('');

        body.querySelectorAll('button[data-id]').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                btn.disabled = true;
                const res = await api.patch('/api/appointments/' + btn.dataset.id, { status: btn.dataset.status });
                btn.disabled = false;
                if (!res.ok) {
                    toast(res.error || '操作失败', 'error');
                    return;
                }
                toast('已更新', 'success');
                load();
            });
        });
    }

    async function load() {
        body.innerHTML = '<tr><td colspan="7" class="empty">加载中…</td></tr>';
        const res = await api.get('/api/appointments' + (currentStatus ? '?status=' + currentStatus : ''));
        if (!res.ok) {
            body.innerHTML = '<tr><td colspan="7" class="empty">' + escapeHtml(res.error || '加载失败') + '</td></tr>';
            return;
        }
        render(res.data.data || []);
    }

    document.querySelectorAll('#statusFilter button').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#statusFilter button').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            currentStatus = btn.dataset.status || '';
            load();
        });
    });

    load();
})();
