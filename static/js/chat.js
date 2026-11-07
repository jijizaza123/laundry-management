/* 员工助手：对话 + 待确认动作卡（写操作必须点确认） */
(function () {
    if (!initShell('chat')) return;
    const box = document.getElementById('chatBox');
    const form = document.getElementById('chatForm');
    const input = document.getElementById('chatInput');
    const send = document.getElementById('chatSend');
    let history = [];

    function bubble(role, text) {
        const div = document.createElement('div');
        div.className = 'chat-msg ' + (role === 'user' ? 'user' : 'assistant');
        div.dataset.raw = text;
        div.textContent = text;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
        return div;
    }

    function actionCard(card) {
        const wrap = document.createElement('div');
        wrap.className = 'chat-action';
        wrap.innerHTML = '<div class="chat-action-title">待确认动作</div>' +
            '<div class="chat-action-summary">' + escapeHtml(card.summary) + '</div>';
        const btn = document.createElement('button');
        btn.className = 'btn btn-primary btn-sm';
        btn.textContent = '确认执行';
        btn.addEventListener('click', async function () {
            btn.disabled = true;
            btn.textContent = '执行中…';
            const res = await api.post('/api/staff/chat', { message: '确认执行', confirm_action_id: card.action_id, history: [] });
            if (!res.ok) {
                btn.disabled = false;
                btn.textContent = '确认执行';
                toast(res.error || '执行失败', 'error');
                return;
            }
            bubble('assistant', res.data.data.answer);
            btn.textContent = '已执行';
            btn.className = 'btn btn-ghost btn-sm';
        });
        wrap.appendChild(btn);
        box.appendChild(wrap);
        box.scrollTop = box.scrollHeight;
    }

    async function ask(text) {
        const res = await api.post('/api/staff/chat', { message: text, history: history.slice(-6) });
        if (!res.ok) {
            toast(res.error || '请求失败', 'error');
            return;
        }
        const data = res.data.data;
        bubble('assistant', data.answer);
        (data.pending_actions || []).forEach(actionCard);
        history.push({ role: 'user', content: text }, { role: 'assistant', content: data.answer });
    }

    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        bubble('user', text);
        input.value = '';
        send.disabled = true;
        send.textContent = '发送中…';
        await ask(text);
        send.disabled = false;
        send.textContent = '发送';
    });

    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            form.requestSubmit();
        }
    });

    document.getElementById('clearChat').addEventListener('click', async function () {
        if (!confirm('清空对话记录？')) return;
        const res = await api.del('/api/staff/chat/history');
        if (!res.ok) {
            toast(res.error || '清空失败', 'error');
            return;
        }
        history = [];
        box.innerHTML = '<div class="chat-msg assistant">已经清空了，重新开始吧。</div>';
    });

    // 刷新后把历史拉回来
    api.get('/api/staff/chat/history').then(function (res) {
        if (!res.ok) return;
        (res.data.data || []).forEach(function (m) {
            bubble(m.role, m.content);
            history.push({ role: m.role, content: m.content });
        });
    });
})();
