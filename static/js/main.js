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

// ── Animated number counters ───────────────────────────────────────────
// Usage: <span class="stat-count" data-target="140" data-decimals="0" data-suffix="+">0</span>
// The counter counts up from 0 to data-target when scrolled into view.
(function() {
    const counters = document.querySelectorAll('.stat-count[data-target]');
    if (!counters.length) return;

    function format(value, decimals) {
        return value.toLocaleString('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        });
    }

    function animate(el) {
        const target   = parseFloat(el.dataset.target);
        const decimals = parseInt(el.dataset.decimals || '0', 10);
        const suffix   = el.dataset.suffix || '';
        const duration = 1800;
        const start    = performance.now();

        function tick(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased    = 1 - Math.pow(1 - progress, 3);
            el.textContent = format(target * eased, decimals) + suffix;
            if (progress < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    if (!('IntersectionObserver' in window)) {
        counters.forEach(animate);
        return;
    }

    const io = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animate(entry.target);
                io.unobserve(entry.target);
            }
        });
    }, { threshold: 0.4 });

    counters.forEach(c => io.observe(c));
})();
