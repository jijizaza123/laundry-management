/* 会员管理 */
var MEMBERS = [];

document.addEventListener('DOMContentLoaded', function () {
    initShell('members');
    loadMembers();
});

function discountPercent(level) {
    const table = { 0: 100, 1: 95, 2: 90, 3: 85, 4: 80 };
    return (table[Number(level || 0)] || 100) + '%';
}

async function loadMembers() {
    const keyword = $('keyword').value.trim();
    const url = '/api/members' + (keyword ? '?keyword=' + encodeURIComponent(keyword) : '');
    const res = await api.get(url);
    const body = $('memberBody');
    if (!res.ok) {
        body.innerHTML = '<tr><td colspan="8" class="empty">' + escapeHtml(res.error) + '</td></tr>';
        return;
    }
    MEMBERS = res.data || [];
    $('countLabel').textContent = '共 ' + MEMBERS.length + ' 位';

    if (!MEMBERS.length) {
        body.innerHTML = '<tr><td colspan="8" class="empty">暂无会员</td></tr>';
        return;
    }

    body.innerHTML = MEMBERS.map(function (m) {
        return '<tr>' +
            '<td class="strong">' + escapeHtml(m.name) + '</td>' +
            '<td class="mono">' + escapeHtml(m.phone) + '</td>' +
            '<td class="muted">' + escapeHtml(m.address || '-') + '</td>' +
            '<td>' + levelBadge(m.member_level) + '</td>' +
            '<td class="mono">' + m.points + '</td>' +
            '<td class="mono">' + discountPercent(m.member_level) + '</td>' +
            '<td class="muted">' + fmtDate(m.created_at) + '</td>' +
            '<td><div class="actions">' +
            '<button class="btn btn-ghost btn-sm" onclick="openEdit(' + m.id + ')">编辑</button>' +
            '<button class="btn btn-ghost btn-sm" onclick="openBind(' + m.id + ')">开账号</button>' +
            '<button class="btn btn-danger btn-sm" onclick="deleteMember(' + m.id + ')">删除</button>' +
            '</div></td>' +
            '</tr>';
    }).join('');
}

function openAdd() {
    $('editTitle').textContent = '新增会员';
    $('editId').value = '';
    $('editName').value = '';
    $('editPhone').value = '';
    $('editAddress').value = '';
    $('editLevel').value = '0';
    $('editPoints').value = '0';
    openModal('editModal');
}

function openEdit(id) {
    const m = MEMBERS.find(function (x) { return x.id === id; });
    if (!m) return;
    $('editTitle').textContent = '编辑会员 · ' + m.name;
    $('editId').value = m.id;
    $('editName').value = m.name;
    $('editPhone').value = m.phone;
    $('editAddress').value = m.address || '';
    $('editLevel').value = String(m.member_level || 0);
    $('editPoints').value = m.points || 0;
    openModal('editModal');
}

async function saveMember() {
    const id = $('editId').value;
    const payload = {
        name: $('editName').value.trim(),
        phone: $('editPhone').value.trim(),
        address: $('editAddress').value.trim(),
        member_level: parseInt($('editLevel').value, 10),
        points: parseInt($('editPoints').value || '0', 10)
    };
    if (!payload.name || !payload.phone) { toast('姓名和手机号必填', 'warn'); return; }

    const res = id
        ? await api.put('/api/members/' + id, payload)
        : await api.post('/api/members', payload);

    if (!res.ok) { toast(res.error, 'error'); return; }
    toast(id ? '已保存' : '已新增会员', 'success');
    closeModal('editModal');
    loadMembers();
}

async function deleteMember(id) {
    const m = MEMBERS.find(function (x) { return x.id === id; });
    if (!m) return;
    if (!confirm('确认删除会员「' + m.name + '」？其历史订单不会被删除')) return;
    const res = await api.del('/api/members/' + id);
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('已删除', 'success');
    loadMembers();
}

/* 为老客户开通客户端账号（客户自己不能认领，必须门店开） */
async function openBind(id) {
    const m = MEMBERS.find(function (x) { return x.id === id; });
    if (!m) return;
    $('bindId').value = m.id;
    $('bindPhone').value = m.phone;
    $('bindPassword').value = '';
    $('bindTitle').textContent = '为「' + m.name + '」开通网店账号';

    const res = await api.get('/api/customers/' + m.id + '/account');
    if (res.ok && res.data && res.data.bound) {
        toast('该客户已有客户端账号：' + res.data.username + '（改密码请用重置流程）', 'warn');
    }
    openModal('bindModal');
}

async function doBind() {
    const id = $('bindId').value;
    const phone = $('bindPhone').value;
    const password = $('bindPassword').value.trim();
    if (password.length < 6) { toast('密码至少 6 位', 'warn'); return; }
    if (/^\d+$/.test(password)) { toast('密码不能是纯数字', 'warn'); return; }

    const res = await api.post('/api/customers/' + id + '/bind-account', { phone: phone, password: password });
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('已开通，客户可用手机号登录客户端', 'success');
    closeModal('bindModal');
}
