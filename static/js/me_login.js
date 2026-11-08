/* 客户端登录 / 注册 */
(function () {
    function tip(id, message, ok) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = message || '';
        el.className = 'me-tip' + (ok ? ' ok' : '');
    }

    function switchTab(name) {
        document.querySelectorAll('#tabs button').forEach(function (b) {
            b.classList.toggle('active', b.dataset.tab === name);
        });
        document.getElementById('loginForm').hidden = name !== 'login';
        document.getElementById('registerForm').hidden = name !== 'register';
    }

    document.querySelectorAll('#tabs button').forEach(function (b) {
        b.addEventListener('click', function () { switchTab(b.dataset.tab); });
    });

    // 已经登录过的客户直接进客户端，不用再看一次登录页
    try {
        const saved = JSON.parse(localStorage.getItem('me_user') || 'null');
        if (localStorage.getItem('me_token') && saved && (!saved.role || saved.role === 'customer')) {
            window.location.href = '/me';
            return;
        }
    } catch (e) { /* 忽略脏数据 */ }

    function saveSession(result) {
        localStorage.setItem('me_token', result.token);
        localStorage.setItem('me_user', JSON.stringify(result.user || {}));
    }

    const loginForm = document.getElementById('loginForm');
    loginForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        const phone = document.getElementById('loginPhone').value.trim();
        const password = document.getElementById('loginPassword').value;
        if (!phone || !password) { tip('loginTip', '请填写手机号和密码'); return; }

        const btn = document.getElementById('loginBtn');
        btn.disabled = true;
        btn.textContent = '登录中…';
        try {
            const res = await api.post('/api/customer/login', { phone: phone, password: password });
            if (!res.ok) { tip('loginTip', res.error || '登录失败'); return; }
            saveSession(res.data);
            window.location.href = '/me';
        } catch (err) {
            tip('loginTip', '网络异常，请稍后重试');
        } finally {
            btn.disabled = false;
            btn.textContent = '登录';
        }
    });

    const registerForm = document.getElementById('registerForm');
    registerForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        const phone = document.getElementById('regPhone').value.trim();
        const name = document.getElementById('regName').value.trim();
        const password = document.getElementById('regPassword').value.trim();
        if (!phone || !password) { tip('registerTip', '手机号和密码都要填'); return; }
        if (password.length < 4) { tip('registerTip', '密码至少 4 位'); return; }

        const btn = document.getElementById('registerBtn');
        btn.disabled = true;
        btn.textContent = '注册中…';
        try {
            const res = await api.post('/api/customer/register', { phone: phone, password: password, name: name || null });
            if (!res.ok) { tip('registerTip', res.error || '注册失败'); return; }

            // 注册成功直接登录，省一次手动操作
            const login = await api.post('/api/customer/login', { phone: phone, password: password });
            if (login.ok) {
                saveSession(login.data);
                const msg = res.data && res.data.existing_archive ? '已关联你的历史消费记录，正在进入…' : '注册成功，正在进入…';
                tip('registerTip', msg, true);
                setTimeout(function () { window.location.href = '/me'; }, 600);
            } else {
                tip('registerTip', '注册成功，请用手机号登录', true);
                switchTab('login');
                document.getElementById('loginPhone').value = phone;
            }
        } catch (err) {
            tip('registerTip', '网络异常，请稍后重试');
        } finally {
            btn.disabled = false;
            btn.textContent = '注册并登录';
        }
    });
})();
