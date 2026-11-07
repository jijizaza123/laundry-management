/* 洗衣助手：把对话发到 /api/my/chat，渲染回答与"查了哪些数据" */
(function () {
    if (!meGuard()) return;

    const log = document.getElementById('chatLog');
    const form = document.getElementById('chatForm');
    const input = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    const quick = document.getElementById('quickAsks');
    const history = [];   // 只保留最近几轮，后端还会再裁一次

    function escapeText(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    /* 轻量渲染：转义后只认 **加粗** 与换行，其它 markdown 符号原样显示 */
    function renderText(text) {
        return escapeText(text)
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    }

    function bubble(role, text) {
        const el = document.createElement('div');
        el.className = 'bubble ' + (role === 'user' ? 'is-user' : 'is-assistant');
        el.innerHTML = '<div class="bubble-text">' + renderText(text) + '</div>';
        log.appendChild(el);
        log.scrollTop = log.scrollHeight;
        return el;
    }

    function toolLine(tools) {
        if (!tools || !tools.length) return null;
        const names = {
            query_my_orders: '查了你的订单列表',
            query_my_order_detail: '查了这单的明细',
            query_my_account: '查了你的会员账户',
            query_care_rule: '查了洗护规则库',
            query_price_list: '查了价目表'
        };
        const el = document.createElement('div');
        el.className = 'bubble-meta';
        el.textContent = tools.map(function (t) { return names[t] || t; }).join(' · ');
        return el;
    }

    async function ask(text) {
        const question = (text || '').trim();
        if (!question) return;
        bubble('user', question);
        input.value = '';
        sendBtn.disabled = true;
        sendBtn.textContent = '查询中…';

        const pending = bubble('assistant', '正在查询…');
        pending.classList.add('is-loading');

        try {
            const res = await api.post('/api/my/chat', {
                message: question,
                history: history.slice(-6)
            });
            if (!res.ok) throw new Error(res.error || '请求失败');
            const data = (res.data && res.data.data) || {};
            pending.remove();

            const answer = (data && data.answer) || '这次没拿到结果，再试一句？';
            const node = bubble('assistant', answer);
            const meta = toolLine(data && data.tools_used);
            if (meta) node.appendChild(meta);
            if (data && data.error) node.classList.add('is-error');

            history.push({ role: 'user', content: question });
            history.push({ role: 'assistant', content: answer });
        } catch (err) {
            pending.remove();
            bubble('assistant', (err && err.message) || '请求失败，稍后再试');
        } finally {
            sendBtn.disabled = false;
            sendBtn.textContent = '发送';
            input.focus();
        }
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        ask(input.value);
    });

    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            ask(input.value);
        }
    });

    quick.addEventListener('click', function (e) {
        const btn = e.target.closest('.chip');
        if (btn) ask(btn.textContent);
    });

    document.getElementById('clearChat').addEventListener('click', async function () {
        const res = await api.del('/api/my/chat/history');
        if (!res.ok) {
            toast(res.error || '清空失败', 'error');
            return;
        }
        history.length = 0;
        while (log.children.length > 1) log.removeChild(log.lastChild);
    });

    // 刷新页面后把服务端存的历史拉回来（不再只存内存）
    api.get('/api/my/chat/history').then(function (res) {
        if (!res.ok) return;
        (res.data.data || []).forEach(function (m) {
            const node = bubble(m.role, m.content);
            const meta = toolLine((m.tools_used || '').split(',').filter(Boolean));
            if (meta) node.appendChild(meta);
            history.push({ role: m.role, content: m.content });
        });
    });
})();
