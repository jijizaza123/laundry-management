/* 统一 API 层：自动附带 JWT、统一解析错误、401 跳登录 */
(function () {
    const rawFetch = window.fetch.bind(window);

    /* 客户端页面（/me 或 /me/xxx）跳客户登录页，管理端跳员工登录页 */
    function loginUrl() {
        return /^\/me(\/|$)/.test(window.location.pathname) ? '/me/login' : '/login';
    }

    function handleAuthLost() {
        const target = loginUrl();
        if (window.location.pathname === target) return;
        localStorage.removeItem('user');
        localStorage.removeItem('token');
        window.location.href = target;
    }

    async function request(url, options) {
        options = options || {};
        const headers = new Headers(options.headers || {});
        const token = localStorage.getItem('token');
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
        const token = localStorage.getItem('token');
        if (token) headers.set('Authorization', 'Bearer ' + token);
        options.headers = headers;
        return rawFetch(url, options).then(function (response) {
            if (response.status === 401) handleAuthLost();
            return response;
        });
    };
})();
