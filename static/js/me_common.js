/* 客户端公共逻辑：登录守卫、等级进度、订单步骤条、明细渲染 */

function meUser() {
    try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch (e) { return null; }
}

function meLogout() {
    localStorage.removeItem('user');
    localStorage.removeItem('token');
    window.location.href = '/me/login';
}

/* 守卫：必须已登录且是客户账号；员工 token 进客户端页面会被劝返 */
function meGuard() {
    const user = meUser();
    const token = localStorage.getItem('token');
    if (!token || !user) {
        window.location.href = '/me/login';
        return null;
    }
    if (user.role && user.role !== 'customer') {
        window.location.href = '/login';
        return null;
    }
    const nameEl = document.getElementById('userName');
    if (nameEl) nameEl.textContent = user.name || user.username || '客户';
    const avatar = document.getElementById('avatar');
    if (avatar) avatar.textContent = (user.name || user.username || '?').slice(0, 1);

    const path = window.location.pathname;
    const page = path === '/me'
        ? 'home'
        : (path.indexOf('/me/chat') === 0 ? 'chat'
            : (path.indexOf('/me/book') === 0 ? 'book'
                : (path.indexOf('/me/messages') === 0 ? 'messages' : 'orders')));
    document.querySelectorAll('#nav a').forEach(function (a) {
        a.classList.toggle('active', a.dataset.page === page);
    });
    document.querySelectorAll('.modal').forEach(function (m) {
        m.addEventListener('click', function (e) {
            if (e.target === m) m.classList.remove('show');
        });
    });
    meRefreshBadge();
    return user;
}

/* 未读消息红点：调价待确认、可取衣都会在这里亮 */
async function meRefreshBadge() {
    const badge = document.getElementById('msgBadge');
    if (!badge) return;
    const res = await api.get('/api/my/notifications?limit=1&unread_only=true');
    if (res.ok && res.data) {
        const n = res.data.unread || 0;
        badge.textContent = n > 99 ? '99+' : String(n);
        badge.style.display = n > 0 ? 'inline-block' : 'none';
    }
}

/* 状态步骤条：已收衣 → 洗涤中 → 可取衣 → 已完成 */
const ME_STEPS = [
    { key: 'received', text: '已收衣' },
    { key: 'washing', text: '洗涤中' },
    { key: 'ready', text: '可取衣' },
    { key: 'completed', text: '已完成' }
];

function meSteps(status) {
    if (status === 'cancelled') {
        return '<div class="me-steps"><div class="me-step" style="flex:2">订单已取消</div></div>';
    }
    const index = ME_STEPS.findIndex(function (s) { return s.key === status; });
    return '<div class="me-steps">' + ME_STEPS.map(function (s, i) {
        let cls = 'me-step';
        if (i < index) cls += ' done';
        if (i === index) cls += ' on';
        return '<div class="' + cls + '">' + s.text + '</div>';
    }).join('') + '</div>';
}

/* 订单明细（只读，无任何操作按钮）。用于表格内联展开，不再用弹窗 */
function renderOrderDetail(order) {
    if (!order) return '<div class="empty">没有数据</div>';
    const items = (order.items_detail || []);
    const rows = items.length
        ? items.map(function (i) {
            return '<tr>' +
                '<td>' + escapeHtml(i.category || '-') + '</td>' +
                '<td>' + escapeHtml(i.service_name || '-') + '</td>' +
                '<td class="mono">' + money(i.unit_price) + '</td>' +
                '<td class="mono">×' + Number(i.quantity || 0) + '</td>' +
                '<td class="mono">' + money(i.subtotal) + '</td>' +
                '</tr>';
        }).join('')
        : '<tr><td colspan="5" class="empty">无明细</td></tr>';

    const logs = order.amount_logs || [];
    const reviewBox = logs.length
        ? '<div class="me-review-box">' +
            logs.map(function (log) {
                return '<div class="me-review-line">门店复核后金额从 ' + money(log.old_total) +
                    ' 调整为 <b>' + money(log.new_total) + '</b>：' + escapeHtml(log.reason || '') + '</div>';
            }).join('') +
            '<button class="btn btn-primary btn-sm" data-confirm="' + order.id + '" data-amount="' +
            (logs[0].new_total) + '">确认新金额 ' + money(logs[0].new_total) + '</button>' +
            '<span class="muted">（不确认就当没同意，取衣时还可以再和师傅核对）</span>' +
          '</div>'
        : '';

    return '' +
        '<div class="me-latest">' +
        meSteps(order.status) +
        '<div class="me-latest-row"><span class="muted">收衣时间</span><span>' + fmtDate(order.receive_time) + '</span></div>' +
        '<div class="me-latest-row"><span class="muted">预计取衣</span><span>' + (fmtDate(order.expected_pickup) || '未预约') + '</span></div>' +
        (order.source === 'online' ? '<div class="me-latest-row"><span class="muted">来源</span><span class="badge">线上下单</span></div>' : '') +
        (order.review_status && order.review_status !== 'confirmed'
            ? '<div class="me-latest-row"><span class="muted">金额状态</span><span class="badge badge-warn">' +
              escapeHtml(order.review_status_text || '') + '</span></div>'
            : '') +
        (order.overdue ? '<div class="me-latest-row"><span class="muted">提醒</span><span class="badge badge-danger">已超过预计取衣日期</span></div>' : '') +
        '</div>' +
        reviewBox +
        '<table class="me-detail-items" style="margin-top:12px">' +
        '<thead><tr><th>分类</th><th>服务</th><th>单价</th><th>数量</th><th>小计</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>' +
        '<div class="summary me-detail-bill">' +
        '<div class="sline"><span>折前金额</span><span>' + money(order.original_amount) + '</span></div>' +
        '<div class="sline"><span>会员折扣</span><span class="cut">' + (Number(order.discount_rate || 1) >= 1
            ? '无折扣'
            : (Number(order.discount_rate) * 10).toFixed(1).replace(/\.0$/, '') + ' 折') +
        (Number(order.discount_amount || 0) > 0 ? '（省 ' + money(order.discount_amount) + '）' : '') + '</span></div>' +
        '<div class="sline"><span>已付</span><span>' + money(order.paid_amount) + '</span></div>' +
        '<div class="sline total"><span>待付</span><span>' + money(order.remaining) + '</span></div>' +
        '</div>';
}
