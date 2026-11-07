async function loadUser() {
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        window.location.href = '/login';
        return;
    }
    const user = JSON.parse(userStr);
    const userNameEl = document.getElementById('userName');
    if (userNameEl) {
        userNameEl.textContent = `欢迎, ${user.name}`;
    }
    return user;
}

function logout() {
    localStorage.removeItem('user');
    localStorage.removeItem('token');
    window.location.href = '/login';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}