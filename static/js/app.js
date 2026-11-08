/* 公共 UI 工具：登录守卫、Toast、徽标、金额格式化、小票 */

const STATUS_META = {
    received: { text: '待洗涤', cls: 'badge-received', next: 'washing', nextText: '开始洗涤' },
    washing: { text: '洗涤中', cls: 'badge-washing', next: 'ready', nextText: '洗涤完成' },
    ready: { text: '可取衣', cls: 'badge-ready', next: null, nextText: null },
    completed: { text: '已完成', cls: 'badge-completed', next: null, nextText: null },
    cancelled: { text: '已取消', cls: 'badge-cancelled', next: null, nextText: null }
};

const LEVEL_NAMES = { 0: '普通客户', 1: '普通会员', 2: '银卡会员', 3: '金卡会员', 4: '钻石会员' };

function $(id) { return document.getElementById(id); }

function money(n) {
    const v = Number(n || 0);
    return '¥' + v.toFixed(2);
}

function num(n) { return Number(n || 0).toFixed(2); }

function fmtDate(s) {
    if (!s) return '-';
    return String(s).replace('T', ' ').slice(0, 16);
}

function statusBadge(status) {
    const meta = STATUS_META[status] || { text: status, cls: 'badge-cancelled' };
    return '<span class="badge ' + meta.cls + '">' + meta.text + '</span>';
}

function levelBadge(level) {
    const lv = Number(level || 0);
    return '<span class="badge lv-' + lv + '">' + (LEVEL_NAMES[lv] || '普通客户') + '</span>';
}

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function toast(message, type) {
    const host = $('toastHost');
    if (!host) { alert(message); return; }
    const el = document.createElement('div');
    el.className = 'toast ' + (type || '');
    el.textContent = message;
    host.appendChild(el);
    setTimeout(function () {
        el.style.opacity = '0';
        el.style.transition = 'opacity .2s';
        setTimeout(function () { el.remove(); }, 220);
    }, 2600);
}

function openModal(id) { const m = $(id); if (m) m.classList.add('show'); }
function closeModal(id) { const m = $(id); if (m) m.classList.remove('show'); }

function getUser() {
    try {
        return JSON.parse(localStorage.getItem('user') || 'null');
    } catch (e) {
        return null;
    }
}

function logout() {
    localStorage.removeItem('user');
    localStorage.removeItem('token');
    window.location.href = '/login';
}

/* 登录守卫 + 顶栏用户信息 + 当前页高亮 */
function initShell(activePage) {
    const user = getUser();
    if (!user || !localStorage.getItem('token')) {
        window.location.href = '/login';
        return null;
    }
    // 客户账号误入管理端页面时，直接送回客户端，避免看到一堆 403
    if (user.role === 'customer') {
        window.location.href = '/me';
        return null;
    }
    const nameEl = $('userName');
    if (nameEl) nameEl.textContent = user.name || user.username || '用户';
    const avatar = $('avatar');
    if (avatar) avatar.textContent = (user.name || user.username || '?').slice(0, 1);

    document.querySelectorAll('#nav a').forEach(function (a) {
        if (a.dataset.page === activePage) a.classList.add('active');
    });
    document.querySelectorAll('.modal').forEach(function (m) {
        m.addEventListener('click', function (e) {
            if (e.target === m) m.classList.remove('show');
        });
    });
    return user;
}

/* 打印小票 */
function renderReceipt(order) {
    const lines = (order.items || '').split('\n').filter(Boolean).map(escapeHtml).join('\n');
    return '' +
        '<div class="receipt">' +
        '<div class="r-title">洗衣店取衣单</div>' +
        '<div class="r-sub">' + escapeHtml(order.order_no) + '</div>' +
        '<div class="r-line"><span>客户</span><span>' + escapeHtml(order.customer_name || '-') + '</span></div>' +
        '<div class="r-line"><span>电话</span><span>' + escapeHtml(order.customer_phone || '-') + '</span></div>' +
        '<div class="r-line"><span>收衣时间</span><span>' + fmtDate(order.receive_time) + '</span></div>' +
        '<div class="r-line"><span>预约取衣</span><span>' + (fmtDate(order.expected_pickup) || '-') + '</span></div>' +
        '<div class="dash"></div>' +
        '<div class="r-items">' + lines + '</div>' +
        '<div class="dash"></div>' +
        '<div class="r-line"><span>折前金额</span><span>' + money(order.original_amount) + '</span></div>' +
        '<div class="r-line"><span>会员折扣</span><span>' + (Number(order.discount_rate || 1) * 100).toFixed(0) + '% 折 ' +
        (Number(order.discount_amount || 0) > 0 ? '（省 ' + money(order.discount_amount) + '）' : '') + '</span></div>' +
        '<div class="r-line"><span>应收</span><span>' + money(order.total_price) + '</span></div>' +
        '<div class="r-line"><span>已收</span><span>' + money(order.paid_amount) + '</span></div>' +
        '<div class="r-line"><span>待收</span><span>' + money(order.remaining) + '</span></div>' +
        '<div class="dash"></div>' +
        '<div class="r-sub">凭本单取衣，请妥善保管</div>' +
        '</div>';
}
