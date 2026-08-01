/**
 * main.js – Shared utilities used across all pages
 * Includes: Toast notifications, smooth scroll, navbar scroll effect
 */

// ── Toast Notification System ───────────────────────────────────────────
window.Kipa = window.Kipa || {};
window.FaceSnap = window.Kipa; // Backward compatibility alias

Kipa.toast = function(message, type = 'info', duration = 4000) {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const icons = { success: '<i class="fa-solid fa-circle-check"></i>', error: '<i class="fa-solid fa-circle-xmark"></i>', info: '<i class="fa-solid fa-circle-info"></i>', warning: '<i class="fa-solid fa-triangle-exclamation"></i>' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-msg">${message}</span>
    `;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('leaving');
        setTimeout(() => toast.remove(), 300);
    }, duration);
};

// ── Navbar scroll effect ────────────────────────────────────────────────
(function() {
    const navbar = document.querySelector('.navbar');
    if (!navbar) return;
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    });
})();
