/* 登录 / 注册 */
document.addEventListener('DOMContentLoaded', function () {
    var saved = getUser();
    // 只有管理端账号才自动进入；客户 token 进管理端会一路 403
    if (localStorage.getItem('token') && saved && saved.role !== 'customer') {
        window.location.href = '/';
        return;
    }

    var loginFormDiv = $('loginFormDiv');
    var registerFormDiv = $('registerFormDiv');
    var loginMsg = $('loginMsg');
    var registerMsg = $('registerMsg');

    function showMsg(el, text, type) {
        el.textContent = text;
        el.className = 'form-msg ' + (type || 'error');
    }

    function hideMsg(el) {
        el.className = 'form-msg';
        el.textContent = '';
    }

    $('toRegister').addEventListener('click', function () {
        loginFormDiv.style.display = 'none';
        registerFormDiv.style.display = 'block';
        hideMsg(loginMsg);
    });

    $('toLogin').addEventListener('click', function () {
        registerFormDiv.style.display = 'none';
        loginFormDiv.style.display = 'block';
        hideMsg(registerMsg);
    });

    $('loginForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        hideMsg(loginMsg);
        var username = $('loginUsername').value.trim();
        var password = $('loginPassword').value;

        var res = await api.post('/api/login', { username: username, password: password });
        if (res.ok && res.data && res.data.success) {
            localStorage.setItem('token', res.data.token);
            localStorage.setItem('user', JSON.stringify(res.data.user));
            showMsg(loginMsg, '登录成功，正在跳转…', 'success');
            window.location.href = '/';
        } else {
            showMsg(loginMsg, res.error || '用户名或密码错误', 'error');
        }
    });

    $('registerForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        hideMsg(registerMsg);
        var payload = {
            username: $('regUsername').value.trim(),
            password: $('regPassword').value,
            name: $('regName').value.trim(),
            invite_code: $('regInvite') ? $('regInvite').value.trim() : ''
        };
        var res = await api.post('/api/register', payload);
        if (res.ok) {
            showMsg(registerMsg, '注册成功，请用新账号登录', 'success');
            setTimeout(function () {
                registerFormDiv.style.display = 'none';
                loginFormDiv.style.display = 'block';
                $('loginUsername').value = payload.username;
                hideMsg(registerMsg);
            }, 1200);
        } else {
            showMsg(registerMsg, res.error || '注册失败', 'error');
        }
    });
});
