/* 线上点单：预约上门取件 + 直接下单（金额由服务端算，前端只做预演） */
(function () {
    if (!meGuard()) return;

    const user = meUser() || {};
    let options = { categories: [], services: [], discount: 1 };
    const rowsBox = document.getElementById('orderRows');

    function moneyText(v) {
        return '¥' + Number(v || 0).toFixed(2);
    }

    function defaultTime(daysAhead) {
        const d = new Date();
        d.setDate(d.getDate() + daysAhead);
        d.setHours(18, 0, 0, 0);
        const pad = (n) => String(n).padStart(2, '0');
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    }

    function toInputTime(text) {
        return (text || '').replace(' ', 'T');
    }

    function fromInputTime(text) {
        return (text || '').replace('T', ' ');
    }

    function addRow(initial) {
        const row = document.createElement('div');
        row.className = 'me-order-row';
        row.innerHTML =
            '<select class="row-category">' + options.categories.map(function (c) {
                return '<option>' + escapeHtml(c) + '</option>';
            }).join('') + '</select>' +
            '<select class="row-service">' + options.services.map(function (s) {
                return '<option data-price="' + s.price + '">' + escapeHtml(s.name) + ' ' + moneyText(s.price) + '</option>';
            }).join('') + '</select>' +
            '<input class="row-qty" type="number" min="1" max="20" value="1">' +
            '<button class="btn btn-ghost btn-sm row-del" type="button">删</button>';
        rowsBox.appendChild(row);
        row.querySelector('.row-del').addEventListener('click', function () {
            if (rowsBox.children.length <= 1) return;
            row.remove();
            refreshQuote();
        });
        row.querySelectorAll('select, input').forEach(function (el) {
            el.addEventListener('change', refreshQuote);
            el.addEventListener('input', refreshQuote);
        });
        if (initial) {
            row.querySelector('.row-category').value = initial.category || row.querySelector('.row-category').value;
            const svc = row.querySelector('.row-service');
            Array.from(svc.options).forEach(function (o) {
                if (o.textContent.indexOf(initial.service_name || '') === 0) svc.value = o.textContent;
            });
            row.querySelector('.row-qty').value = initial.quantity || 1;
        }
        refreshQuote();
        return row;
    }

    function collectRows() {
        return Array.from(rowsBox.querySelectorAll('.me-order-row')).map(function (row) {
            const svc = row.querySelector('.row-service').value.split(' ')[0];
            return {
                category: row.querySelector('.row-category').value || '未分类',
                service_name: svc,
                quantity: Number(row.querySelector('.row-qty').value || 1)
            };
        }).filter(function (r) { return r.service_name && r.quantity > 0; });
    }

    let quoteTimer = null;
    function refreshQuote() {
        clearTimeout(quoteTimer);
        quoteTimer = setTimeout(async function () {
            const rows = collectRows();
            if (!rows.length) return;
            const res = await api.post('/api/my/quote', { items_detail: rows });
            if (!res.ok) return;
            const q = res.data.data;
            document.getElementById('quoteSubtotal').textContent = moneyText(q.subtotal);
            document.getElementById('quoteDiscount').textContent = Number(q.discount_rate || 1) >= 1
                ? '无折扣'
                : (Number(q.discount_rate) * 10).toFixed(1).replace(/\.0$/, '') + ' 折';
            document.getElementById('quoteTotal').textContent = moneyText(q.total);
            document.getElementById('orderSubmit').dataset.total = String(q.total);
        }, 220);
    }

    async function loadOptions() {
        const res = await api.get('/api/my/options');
        if (!res.ok) {
            rowsBox.innerHTML = '<div class="empty">选项加载失败：' + escapeHtml(res.error || '') + '</div>';
            return;
        }
        options = res.data.data;
        addRow();
    }

    async function loadAppointments() {
        const box = document.getElementById('apptList');
        const res = await api.get('/api/my/appointments');
        if (!res.ok) {
            box.innerHTML = '<div class="empty">' + escapeHtml(res.error || '加载失败') + '</div>';
            return;
        }
        const rows = res.data.data || [];
        if (!rows.length) {
            box.innerHTML = '<div class="empty">还没有预约记录</div>';
            return;
        }
        box.innerHTML = rows.map(function (a) {
            return '<div class="me-appt">' +
                '<div class="me-appt-main"><b>' + escapeHtml(a.expected_time) + '</b> · ' +
                escapeHtml(a.status_text) + '</div>' +
                '<div class="me-appt-sub">' + escapeHtml(a.address) +
                (a.note ? '｜' + escapeHtml(a.note) : '') + '</div>' +
                '<div class="me-appt-sub mono">' + escapeHtml(a.appt_no) + '</div>' +
                '</div>';
        }).join('');
    }

    document.getElementById('addRow').addEventListener('click', function () { addRow(); });

    document.getElementById('apptForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        const btn = document.getElementById('apptSubmit');
        btn.disabled = true;
        btn.textContent = '提交中…';
        const payload = {
            expected_time: fromInputTime(document.getElementById('apptTime').value),
            address: document.getElementById('apptAddress').value,
            note: document.getElementById('apptNote').value
        };
        const res = await api.post('/api/my/appointments', payload);
        btn.disabled = false;
        btn.textContent = '提交预约';
        if (!res.ok) {
            toast(res.error || '预约失败', 'error');
            return;
        }
        toast('预约已提交，等师傅联系你', 'success');
        document.getElementById('apptNote').value = '';
        loadAppointments();
    });

    document.getElementById('orderForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        const btn = document.getElementById('orderSubmit');
        const rows = collectRows();
        if (!rows.length) {
            toast('至少选一件衣服', 'error');
            return;
        }
        btn.disabled = true;
        btn.textContent = '提交中…';

        let appointmentId = null;
        if (document.getElementById('withAppointment').checked) {
            const apptRes = await api.post('/api/my/appointments', {
                expected_time: fromInputTime(document.getElementById('apptTime').value || defaultTime(1)),
                address: document.getElementById('apptAddress').value,
                note: document.getElementById('apptNote').value || '下单时顺带预约'
            });
            if (!apptRes.ok) {
                btn.disabled = false;
                btn.textContent = '提交订单';
                toast('预约没建成：' + (apptRes.error || '请检查地址和时间'), 'error');
                return;
            }
            appointmentId = apptRes.data.data.id;
        }

        const res = await api.post('/api/my/orders', {
            items_detail: rows,
            expected_pickup: fromInputTime(document.getElementById('pickupTime').value) || null,
            appointment_id: appointmentId
        });
        btn.disabled = false;
        btn.textContent = '提交订单';
        if (!res.ok) {
            toast(res.error || '下单失败', 'error');
            return;
        }
        toast('下单成功，到店复核后金额才最终确定', 'success');
        setTimeout(function () { window.location.href = '/me/orders'; }, 1200);
    });

    document.getElementById('apptTime').value = toInputTime(defaultTime(1));
    loadOptions();
    loadAppointments();
})();
