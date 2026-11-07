/* 库存管理 */
var INVENTORY = [];
var moveMode = null; /* {type:'in'|'out', id:number} */

document.addEventListener('DOMContentLoaded', function () {
    initShell('inventory');
    loadInventory();
});

async function loadInventory() {
    const res = await api.get('/api/inventory');
    const body = $('invBody');
    if (!res.ok) {
        body.innerHTML = '<tr><td colspan="6" class="empty">' + escapeHtml(res.error) + '</td></tr>';
        return;
    }
    INVENTORY = res.data || [];
    $('countLabel').textContent = '共 ' + INVENTORY.length + ' 条';
    $('iKinds').textContent = INVENTORY.length;
    $('iLow').textContent = INVENTORY.filter(function (i) { return i.quantity <= 5; }).length;
    $('iValue').textContent = money(INVENTORY.reduce(function (s, i) { return s + i.quantity * i.price; }, 0));

    if (!INVENTORY.length) {
        body.innerHTML = '<tr><td colspan="6" class="empty">还没有耗材记录，先新增一条</td></tr>';
        return;
    }

    body.innerHTML = INVENTORY.map(function (i) {
        const low = i.quantity <= 5;
        return '<tr>' +
            '<td class="strong">' + escapeHtml(i.name) + '</td>' +
            '<td class="mono">' + i.quantity + ' ' + escapeHtml(i.unit || '') + '</td>' +
            '<td class="muted">' + escapeHtml(i.unit || '-') + '</td>' +
            '<td class="mono">' + money(i.price) + '</td>' +
            '<td>' + (low ? '<span class="badge badge-danger">库存偏低</span>' : '<span class="badge badge-completed">充足</span>') + '</td>' +
            '<td><div class="actions">' +
            '<button class="btn btn-ghost btn-sm" onclick="openMove(\'in\',' + i.id + ')">入库</button>' +
            '<button class="btn btn-ghost btn-sm" onclick="openMove(\'out\',' + i.id + ')">出库</button>' +
            '<button class="btn btn-danger btn-sm" onclick="removeItem(' + i.id + ')">删除</button>' +
            '</div></td>' +
            '</tr>';
    }).join('');
}

function openAdd() {
    moveMode = null;
    $('invTitle').textContent = '新增耗材';
    $('invForm').style.display = 'block';
    $('moveForm').style.display = 'none';
    $('invName').value = '';
    $('invQty').value = '0';
    $('invUnit').value = '瓶';
    $('invPrice').value = '0';
    openModal('invModal');
}

function openMove(type, id) {
    const item = INVENTORY.find(function (i) { return i.id === id; });
    if (!item) return;
    moveMode = { type: type, id: id };
    $('invTitle').textContent = (type === 'in' ? '入库 · ' : '出库 · ') + item.name;
    $('invForm').style.display = 'none';
    $('moveForm').style.display = 'block';
    $('moveHint').textContent = '当前库存：' + item.quantity + ' ' + (item.unit || '');
    $('moveQty').value = '1';
    openModal('invModal');
}

async function submitInv() {
    if (moveMode) {
        const qty = parseInt($('moveQty').value || '0', 10);
        if (qty <= 0) { toast('数量必须大于 0', 'warn'); return; }
        const url = '/api/inventory/' + moveMode.id + '/' + moveMode.type + '?quantity=' + qty;
        const res = await api.post(url, {});
        if (!res.ok) { toast(res.error, 'error'); return; }
        toast((moveMode.type === 'in' ? '入库' : '出库') + '成功，剩余 ' + res.data.quantity + (res.data.unit || ''), 'success');
        closeModal('invModal');
        moveMode = null;
        loadInventory();
        return;
    }

    const payload = {
        name: $('invName').value.trim(),
        quantity: parseInt($('invQty').value || '0', 10),
        unit: $('invUnit').value.trim() || '件',
        price: parseFloat($('invPrice').value || '0')
    };
    if (!payload.name) { toast('请填写耗材名称', 'warn'); return; }
    const res = await api.post('/api/inventory', payload);
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('已新增', 'success');
    closeModal('invModal');
    loadInventory();
}

async function removeItem(id) {
    const item = INVENTORY.find(function (i) { return i.id === id; });
    if (!item) return;
    if (!confirm('确认删除耗材「' + item.name + '」？')) return;
    const res = await api.del('/api/inventory/' + id);
    if (!res.ok) { toast(res.error, 'error'); return; }
    toast('已删除', 'success');
    loadInventory();
}
