/* Agent 指标看板 */
document.addEventListener('DOMContentLoaded', function () {
    initShell('metrics');
    loadMetrics();
});

const SIDE_TEXT = { customer: '客户端助手', staff: '员工助手' };

async function loadMetrics() {
    const days = $('days').value;
    const res = await api.get('/api/staff/metrics?days=' + days);
    const body = $('metricBody');
    const recent = $('recentBody');
    if (!res.ok) {
        body.innerHTML = '<tr><td colspan="10" class="empty">' + escapeHtml(res.error) + '</td></tr>';
        recent.innerHTML = '<tr><td colspan="7" class="empty">—</td></tr>';
        return;
    }
    const payload = res.data || {};
    const data = payload.data || payload;
    $('rangeLabel').textContent = data.start_date + ' ~ ' + data.end_date;

    const sides = data.sides || [];
    if (!sides.length) {
        body.innerHTML = '<tr><td colspan="10" class="empty">这段时间还没有调用记录</td></tr>';
    } else {
        body.innerHTML = sides.map(function (s) {
            return '<tr>' +
                '<td class="strong">' + (SIDE_TEXT[s.side] || s.side) + '</td>' +
                '<td class="mono">' + s.calls + '</td>' +
                '<td class="mono">' + s.errors + '</td>' +
                '<td class="mono">' + (s.error_rate * 100).toFixed(1) + '%</td>' +
                '<td class="mono">' + s.avg_ms + ' ms</td>' +
                '<td class="mono">' + s.p50_ms + ' ms</td>' +
                '<td class="mono">' + s.p95_ms + ' ms</td>' +
                '<td class="mono">' + s.max_ms + ' ms</td>' +
                '<td class="mono">' + s.avg_rounds + '</td>' +
                '<td class="mono">' + s.tool_calls + '</td>' +
                '</tr>';
        }).join('');
    }

    const rows = data.recent || [];
    if (!rows.length) {
        recent.innerHTML = '<tr><td colspan="7" class="empty">暂无记录</td></tr>';
        return;
    }
    recent.innerHTML = rows.map(function (r) {
        return '<tr>' +
            '<td class="muted">' + fmtDate(r.created_at) + '</td>' +
            '<td>' + (SIDE_TEXT[r.side] || r.side) + '</td>' +
            '<td class="muted">' + escapeHtml((r.question || '').slice(0, 40)) + '</td>' +
            '<td class="muted mono">' + escapeHtml((r.tools || []).join(', ') || '-') + '</td>' +
            '<td class="mono">' + r.rounds + '</td>' +
            '<td class="mono">' + r.elapsed_ms + ' ms</td>' +
            '<td>' + (r.ok ? '<span class="badge badge-completed">正常</span>' : '<span class="badge badge-danger">出错</span>') + '</td>' +
            '</tr>';
    }).join('');
}
