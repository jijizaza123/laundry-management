/* 统一 API 层：自动附带 JWT、统一解析错误、401 跳登录 */
(function () {
    const rawFetch = window.fetch.bind(window);

    /* 客户端页面（/me 或 /me/xxx）跳客户登录页，管理端跳员工登录页 */
    function loginUrl() {
        return /^\/me(\/|$)/.test(window.location.pathname) ? '/me/login' : '/login';
    }

    /* 两端的登录态必须分开存：早期共用 token 时，客户登录后打开管理端页面
       会带着客户 token 去请求 /api/stats，直接吃 403 弹一个红色提示 */
    function isMe() { return /^\/me(\/|$)/.test(window.location.pathname); }
    function tokenKey() { return isMe() ? 'me_token' : 'token'; }
    function userKey() { return isMe() ? 'me_user' : 'user'; }

    function handleAuthLost() {
        const target = loginUrl();
        if (window.location.pathname === target) return;
        localStorage.removeItem(userKey());
        localStorage.removeItem(tokenKey());
        window.location.href = target;
    }

    async function request(url, options) {
        options = options || {};
        const headers = new Headers(options.headers || {});
        const token = localStorage.getItem(tokenKey());
        if (token) headers.set('Authorization', 'Bearer ' + token);
        if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
        options.headers = headers;

        const response = await rawFetch(url, options);
        let data = null;
        try {
            data = await response.json();
        } catch (e) {
            data = null;
        }

        if (response.status === 401) handleAuthLost();

        const error = !response.ok
            ? (data && (data.error || data.message || (typeof data.detail === 'string' ? data.detail : null))) || ('请求失败（' + response.status + '）')
            : null;

        return { ok: response.ok, status: response.status, data: data, error: error };
    }

    window.api = {
        request: request,
        key: tokenKey,
        userKey: userKey,
        get: function (url) { return request(url, { method: 'GET' }); },
        post: function (url, body) { return request(url, { method: 'POST', body: JSON.stringify(body || {}) }); },
        put: function (url, body) { return request(url, { method: 'PUT', body: JSON.stringify(body || {}) }); },
        patch: function (url, body) { return request(url, { method: 'PATCH', body: JSON.stringify(body || {}) }); },
        del: function (url) { return request(url, { method: 'DELETE' }); }
    };

    /* 兼容旧代码里直接调用 fetch 的写法 */
    window.fetch = function (url, options) {
        options = options || {};
        const headers = new Headers(options.headers || {});
        const token = localStorage.getItem(tokenKey());
        if (token) headers.set('Authorization', 'Bearer ' + token);
        options.headers = headers;
        return rawFetch(url, options).then(function (response) {
            if (response.status === 401) handleAuthLost();
            return response;
        });
    };

    /* 一次性迁移：老用户浏览器里只存了 token/user，登录过客户端的会带着客户 token
       去管理端，这里按 user.role 把它们归位，旧键清掉，避免继续互相干扰 */
    (function migrateLegacy() {
        const legacyUser = localStorage.getItem('user');
        const legacyToken = localStorage.getItem('token');
        if (!legacyUser || !legacyToken) return;
        let role = '';
        try { role = (JSON.parse(legacyUser) || {}).role || ''; } catch (e) { role = ''; }
        if (role === 'customer') {
            if (!localStorage.getItem('me_token')) {
                localStorage.setItem('me_token', legacyToken);
                localStorage.setItem('me_user', legacyUser);
            }
            localStorage.removeItem('token');
            localStorage.removeItem('user');
        }
    })();
})();
