/* 收衣建单：明细 → 服务端试算 → 提交 */
var CATEGORIES = [];
var SERVICES = [];
var quoteTimer = null;

document.addEventListener('DOMContentLoaded', async function () {
    initShell('receive');
    await Promise.all([loadCategories(), loadServices()]);
    addItemRow();
    const d = new Date();
    d.setDate(d.getDate() + 1); // 默认预约到明天，避免一收衣就逾期
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    $('expectedPickup').value = d.toISOString().slice(0, 10) + 'T18:00';
    refreshQuote();
});

async function loadCategories() {
    const res = await api.get('/api/categories');
    CATEGORIES = res.ok ? res.data : [];
}

async function loadServices() {
    const res = await api.get('/api/services');
    SERVICES = res.ok ? res.data : [];
}

function serviceOptions(selected) {
    return '<option value="">选择服务</option>' + SERVICES.map(function (s) {
        return '<option value="' + escapeHtml(s.name) + '"' + (selected === s.name ? ' selected' : '') + '>' +
            escapeHtml(s.name) + '（¥' + s.price + '/' + escapeHtml(s.unit) + '）</option>';
    }).join('');
}

function categoryOptions(selected) {
    return '<option value="">选择分类</option>' + CATEGORIES.map(function (c) {
        return '<option value="' + escapeHtml(c.name) + '"' + (selected === c.name ? ' selected' : '') + '>' +
            escapeHtml(c.name) + '</option>';
    }).join('');
}

function addItemRow() {
    const list = $('itemsList');
    const row = document.createElement('div');
    row.className = 'item-row';
    row.innerHTML =
        '<select class="select input-sm category-select">' + categoryOptions('') + '</select>' +
        '<select class="select input-sm service-select" onchange="onServiceChange(this)">' + serviceOptions('') + '</select>' +
        '<input class="input input-sm qty-input" type="number" min="1" value="1" onchange="refreshQuote()">' +
        '<div class="price-cell mono">¥0.00</div>' +
        '<button class="btn btn-danger btn-sm btn-icon" title="删除" onclick="removeItemRow(this)">×</button>';
    list.appendChild(row);
    refreshQuote();
}

function removeItemRow(btn) {
    const rows = document.querySelectorAll('#itemsList .item-row');
    if (rows.length <= 1) { toast('至少保留一项衣物', 'warn'); return; }
    btn.closest('.item-row').remove();
    refreshQuote();
}

function onServiceChange(select) {
    const row = select.closest('.item-row');
    const priceCell = row.querySelector('.price-cell');
    const service = SERVICES.find(function (s) { return s.name === select.value; });
    const qty = parseInt(row.querySelector('.qty-input').value || '0', 10);
    priceCell.textContent = money(service ? service.price * qty : 0);
    refreshQuote();
}

function collectItems() {
    const rows = Array.prototype.slice.call(document.querySelectorAll('#itemsList .item-row'));
    const items = [];
    rows.forEach(function (row) {
        const category = row.querySelector('.category-select').value;
        const service = row.querySelector('.service-select').value;
        const qty = parseInt(row.querySelector('.qty-input').value || '0', 10);
        if (service && qty > 0) {
            items.push({ category: category || '未分类', service_name: service, quantity: qty });
        }
        const priceCell = row.querySelector('.price-cell');
        const svc = SERVICES.find(function (s) { return s.name === service; });
        priceCell.textContent = money(svc ? svc.price * (qty || 0) : 0);
    });
    return items;
}

function onPhoneInput() {
    const phone = $('customerPhone').value.trim();
    if (phone.length >= 6) {
        clearTimeout(quoteTimer);
        quoteTimer = setTimeout(refreshQuote, 400);
    }
}

async function queryCustomer() {
    const phone = $('customerPhone').value.trim();
    if (!phone) { toast('请先输入手机号', 'warn'); return; }
    const res = await api.get('/api/customers?keyword=' + encodeURIComponent(phone));
    if (!res.ok) { toast(res.error, 'error'); return; }
    const list = res.data || [];
    const hit = list.find(function (c) { return c.phone === phone; });
    const box = $('memberInfo');
    if (hit) {
        box.style.display = 'block';
        $('customerName').value = hit.name;
        $('memberBadge').outerHTML = '<span id="memberBadge" class="badge lv-' + hit.member_level + '">' + hit.level_name + '</span>';
        $('memberPoints').textContent = hit.points;
        $('memberDiscount').textContent = discountPercent(hit.member_level) + '%';
        toast('已识别会员：' + hit.name, 'success');
    } else {
        box.style.display = 'none';
        toast('未找到该手机号的客户，将自动建档', 'warn');
    }
    refreshQuote();
}

function discountPercent(level) {
    const table = { 0: 100, 1: 95, 2: 90, 3: 85, 4: 80 };
    return table[Number(level || 0)] || 100;
}

async function refreshQuote() {
    const items = collectItems();
    const phone = $('customerPhone').value.trim();
    const deposit = parseFloat($('deposit').value || '0') || 0;

    if (!items.length) {
        $('qSubtotal').textContent = money(0);
        $('qTotal').textContent = money(0);
        $('qDiscount').textContent = '-¥0.00';
        $('qDeposit').textContent = money(0);
        $('qRemaining').textContent = money(0);
        return;
    }

    const res = await api.post('/api/orders/quote', { items_detail: items, customer_phone: phone || null });
    if (!res.ok) {
        toast(res.error, 'error');
        return;
    }
    const q = res.data;
    $('qSubtotal').textContent = money(q.subtotal);
    $('qRate').textContent = Math.round(q.discount_rate * 100) + '%';
    $('qDiscount').textContent = '-' + money(q.discount_amount);
    $('qTotal').textContent = money(q.total);
    $('qDeposit').textContent = money(deposit);
    $('qRemaining').textContent = money(Math.max(q.total - deposit, 0));
    $('quoteLevel').textContent = q.level_name + '（' + Math.round(q.discount_rate * 100) + '% 计价）';
}

async function submitOrder() {
    const name = $('customerName').value.trim();
    const phone = $('customerPhone').value.trim();
    const items = collectItems();

    if (!phone) { toast('请填写客户手机号', 'warn'); return; }
    if (!name) { toast('请填写客户姓名', 'warn'); return; }
    if (!items.length) { toast('请至少添加一项衣物', 'warn'); return; }

    const btn = $('submitBtn');
    btn.disabled = true;

    const expected = $('expectedPickup').value;
    const payload = {
        customer_name: name,
        customer_phone: phone,
        items_detail: items,
        deposit: parseFloat($('deposit').value || '0') || 0,
        pay_now: $('payNow').checked,
        expected_pickup: expected ? expected.replace('T', ' ') + (expected.length === 16 ? ':00' : '') : null
    };

    const res = await api.post('/api/orders', payload);
    btn.disabled = false;

    if (!res.ok) {
        toast(res.error || '建单失败', 'error');
        return;
    }

    $('receiptBody').innerHTML = renderReceipt(res.data);
    openModal('receiptModal');
    toast('收衣成功：' + res.data.order_no, 'success');
    resetForm();
}

function resetForm() {
    $('customerName').value = '';
    $('customerPhone').value = '';
    $('memberInfo').style.display = 'none';
    $('deposit').value = '0';
    $('itemsList').innerHTML = '';
    addItemRow();
    refreshQuote();
}
