/* 我的首页：概览 + 会员卡 + 最近一单 + 进行中订单 */
(function () {
    if (!meGuard()) return;

    function levelPercent(points, nextLevel) {
        // 用"当前等级门槛 → 下一等级门槛"之间的进度做可视化
        const thresholds = { 0: 0, 1: 100, 2: 300, 3: 800, 4: 1500 };
        const lv = Number(nextLevel && nextLevel.level ? nextLevel.level - 1 : 4);
        if (!nextLevel || nextLevel.at_top) return 100;
        const from = thresholds[lv] != null ? thresholds[lv] : 0;
        const to = points + (nextLevel.need_points || 0);
        if (to <= from) return 100;
        const pct = Math.max(0, Math.min(100, (points - from) / (to - from) * 100));
        return Math.round(pct);
    }

    function renderProfile(profile) {
        document.getElementById('helloName').textContent = profile.name || '客户';
        document.getElementById('phoneText').textContent = profile.phone || '-';
        document.getElementById('addressText').textContent = profile.address || '未登记';
        document.getElementById('pointsText').textContent = String(profile.points || 0);
        const rate = Number(profile.discount || 1);
        document.getElementById('discountText').textContent = rate >= 1
            ? '原价消费，暂无折扣'
            : ('享 ' + (rate * 10).toFixed(1).replace(/\.0$/, '') + ' 折');

        const badge = document.getElementById('levelBadge');
        badge.className = 'badge lv-' + (profile.member_level || 0);
        badge.textContent = profile.level_name || '普通客户';

        const next = profile.next_level || {};
        const bar = document.getElementById('levelBar');
        bar.style.width = levelPercent(profile.points || 0, next) + '%';
        document.getElementById('levelHint').textContent = next.at_top
            ? '已是最高等级，积分继续累加'
            : ('再消费 ' + (next.need_points || 0) + ' 元可升级为' + (next.level_name || '下一等级'));
    }

    function renderSummary(data) {
        document.getElementById('kpiActive').textContent = data.active_count || 0;
        document.getElementById('kpiReady').textContent = data.ready_count || 0;
        document.getElementById('kpiUnpaid').textContent = money(data.unpaid_amount);
        document.getElementById('kpiSpent').textContent = money(data.total_spent);

        const latestBox = document.getElementById('latestBox');
        const latest = data.latest_order;
        if (!latest) {
            latestBox.innerHTML = '<div class="empty">还没有订单记录，到店收衣后就能看到</div>';
        } else {
            latestBox.innerHTML = '' +
                '<div class="me-latest-row"><span class="me-latest-no">' + escapeHtml(latest.order_no) + '</span>' +
                statusBadge(latest.status) + '</div>' +
                meSteps(latest.status) +
                '<div class="me-latest-row"><span class="muted">件数 · 应收</span>' +
                '<span>' + (latest.item_count || 0) + ' 件 · ' + money(latest.total_price) + '</span></div>' +
                '<div class="me-latest-row"><span class="muted">预计取衣</span>' +
                '<span>' + (fmtDate(latest.expected_pickup) || '未预约') + '</span></div>' +
                (latest.overdue ? '<div class="me-latest-row"><span class="muted">提醒</span><span class="badge badge-danger">已超过预计取衣日期</span></div>' : '') +
                '<a class="btn btn-ghost btn-sm" href="/me/orders?order=' + latest.id + '">查看明细</a>';
        }

        renderActive(data.active_list || []);
    }

    function renderActive(rows) {
        const body = document.getElementById('activeBody');
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="7" class="empty">暂无在店衣物</td></tr>';
            return;
        }
        body.innerHTML = rows.map(function (o) {
            return '<tr data-id="' + o.id + '" style="cursor:pointer">' +
                '<td class="mono">' + escapeHtml(o.order_no) + '</td>' +
                '<td>' + escapeHtml((o.items || '').split('\n')[0] || '-') + '</td>' +
                '<td class="mono">' + (o.item_count || 0) + '</td>' +
                '<td class="mono">' + money(o.total_price) + '</td>' +
                '<td class="mono">' + money(o.remaining) + '</td>' +
                '<td>' + statusBadge(o.status) + '</td>' +
                '<td>' + (fmtDate(o.expected_pickup) || '未预约') + '</td>' +
                '</tr>';
        }).join('');
        body.querySelectorAll('tr[data-id]').forEach(function (tr) {
            tr.addEventListener('click', function () {
                window.location.href = '/me/orders?order=' + tr.dataset.id;
            });
        });
    }

    window.meOpenDetail = null;

    async function load() {
        const res = await api.get('/api/my/summary');
        if (!res.ok) {
            if (res.status !== 401) toast(res.error || '加载失败');
            return;
        }
        const data = res.data.data;
        renderProfile(data.profile);
        // 进行中订单单独拉一次，确保顺序与状态最新
        const list = await api.get('/api/my/orders?status=&limit=20');
        const active = (list.ok ? list.data.data : []).filter(function (o) {
            return o.status === 'received' || o.status === 'washing' || o.status === 'ready';
        });
        data.active_list = active;
        renderSummary(data);
    }

    load();
})();
