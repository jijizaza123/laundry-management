/* 我的消息：门店调价待确认、衣服可取、预约状态变化 */
(function () {
    if (!meGuard()) return;

    const list = document.getElementById('msgList');

    const TYPE_CLASS = {
        price_adjusted: 'badge-warn',
        ready: 'badge-ok',
        appointment: 'badge-info',
        cancelled: 'badge-muted',
        info: 'badge-muted'
    };

    function render(rows) {
        if (!rows.length) {
            list.innerHTML = '<div class="empty">还没有消息。门店调价、衣服可取时会推到这里。</div>';
            return;
        }
        list.innerHTML = rows.map(function (n) {
            const unread = !n.is_read;
            return '<div class="msg-item' + (unread ? ' unread' : '') + '">' +
                '<div class="msg-head">' +
                '<span class="badge ' + (TYPE_CLASS[n.type] || 'badge-muted') + '">' + escapeHtml(n.type_text || '通知') + '</span>' +
                '<strong>' + escapeHtml(n.title || '') + '</strong>' +
                (unread ? '<span class="dot"></span>' : '') +
                '<span class="msg-time">' + fmtDate(n.created_at) + '</span>' +
                '</div>' +
                '<p>' + escapeHtml(n.body || '') + '</p>' +
                (n.order_id ? '<a class="link-btn" href="/me/orders">去我的订单看</a>' : '') +
                '</div>';
        }).join('');
    }

    async function load() {
        const res = await api.get('/api/my/notifications?limit=50');
        if (!res.ok) {
            list.innerHTML = '<div class="empty">' + escapeHtml(res.error || '加载失败') + '</div>';
            return;
        }
        const body = res.data || {};
        render(body.data || []);
        meRefreshBadge();
    }

    document.getElementById('readAll').addEventListener('click', async function () {
        const res = await api.post('/api/my/notifications/read', {});
        if (res.ok) {
            toast('已全部标为已读');
            load();
        } else {
            toast(res.error || '操作失败');
        }
    });

    load();
})();
