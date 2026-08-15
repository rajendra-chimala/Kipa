/**
 * main.js – Shared utilities used across all pages
 * Includes: Toast notifications, smooth scroll, navbar scroll effect
 */

// ── Fade-Up Scroll Reveal (site-wide) ────────────────────────────────────
// Usage: <div class="fade-up d-2">…</div> — element fades/slides up into
// view the first time it scrolls into the viewport.
(function() {
    document.documentElement.classList.add('js');

    const els = document.querySelectorAll('.fade-up');
    if (!els.length) return;

    const reveal = (el) => el.classList.add('fade-up-visible');

    if (!('IntersectionObserver' in window)) {
        els.forEach(reveal);
        return;
    }

    const io = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                reveal(entry.target);
                io.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12, rootMargin: '0px 0px -48px 0px' });

    els.forEach(el => io.observe(el));
})();

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

// ── FAQ Scroll-Stack (react-bits ScrollStack, vanilla port) ──
// Turns the home-page FAQ into a deck of cards that pin to the
// top of a dedicated overflow container and pile into a stack
// while the user scrolls inside it. Uses Lenis when available
// and falls back to native scrolling otherwise.
(function() {
    const scroller = document.querySelector('.faq-stack-scroller');
    if (!scroller) return;

    const reduceMotion = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const cards = Array.from(scroller.querySelectorAll('.scroll-stack-card'));
    const inner = scroller.querySelector('.scroll-stack-inner');
    const endEl = scroller.querySelector('.scroll-stack-end');
    if (!inner || !endEl || !cards.length) return;

    const CFG = {
        itemDistance: 56,
        itemScale: 0.03,
        itemStackDistance: 24,
        stackPosition: 0.12,
        scaleEndPosition: 0.05,
        baseScale: 0.9,
        rotationAmount: 2,
        blurAmount: 4
    };

    const lastTransforms = new Map();
    let updating = false;
    let rafId = null;
    let lenis = null;

    const spPx = () => CFG.stackPosition * (scroller.clientHeight || 1);
    const pinStartOf = i => cards[i].offsetTop - spPx() - CFG.itemStackDistance * i;

    function update() {
        if (updating) return;
        updating = true;

        const scrollTop = scroller.scrollTop;
        const h = scroller.clientHeight || 1;
        const sPx = CFG.stackPosition * h;
        const ePx = CFG.scaleEndPosition * h;
        const endTop = endEl.offsetTop;

        cards.forEach((card, i) => {
            const cardTop = card.offsetTop;
            const triggerStart = cardTop - sPx - CFG.itemStackDistance * i;
            const triggerEnd = cardTop - ePx;
            const pinStart = triggerStart;
            const pinEnd = endTop - h / 2;

            const range = triggerEnd - triggerStart || 1;
            const progress = Math.min(Math.max((scrollTop - triggerStart) / range, 0), 1);
            const targetScale = CFG.baseScale + i * CFG.itemScale;
            const scale = 1 - progress * (1 - targetScale);
            const rotation = CFG.rotationAmount ? i * CFG.rotationAmount * progress : 0;

            let blur = 0;
            if (CFG.blurAmount) {
                let topCard = 0;
                for (let j = 0; j < cards.length; j++) {
                    const jStart = cards[j].offsetTop - sPx - CFG.itemStackDistance * j;
                    if (scrollTop >= jStart) topCard = j;
                }
                if (i < topCard) blur = Math.max(0, (topCard - i) * CFG.blurAmount);
            }

            let translateY = 0;
            if (scrollTop >= pinStart && scrollTop <= pinEnd) {
                translateY = scrollTop - cardTop + sPx + CFG.itemStackDistance * i;
            } else if (scrollTop > pinEnd) {
                translateY = pinEnd - cardTop + sPx + CFG.itemStackDistance * i;
            }

            const next = {
                ty: Math.round(translateY * 100) / 100,
                sc: Math.round(scale * 1000) / 1000,
                ro: Math.round(rotation * 100) / 100,
                bl: Math.round(blur * 100) / 100
            };
            const prev = lastTransforms.get(i);
            const changed = !prev ||
                Math.abs(prev.ty - next.ty) > 0.1 ||
                Math.abs(prev.sc - next.sc) > 0.001 ||
                Math.abs(prev.ro - next.ro) > 0.1 ||
                Math.abs(prev.bl - next.bl) > 0.1;

            if (changed) {
                card.style.transform =
                    'translate3d(0,' + next.ty + 'px,0) scale(' + next.sc + ') rotate(' + next.ro + 'deg)';
                card.style.filter = next.bl > 0 ? 'blur(' + next.bl + 'px)' : '';
                lastTransforms.set(i, next);
            }
        });

        updating = false;
    }

    const sync = () => { lastTransforms.clear(); update(); };

    function setupCards() {
        cards.forEach((card, i) => {
            if (i < cards.length - 1) card.style.marginBottom = CFG.itemDistance + 'px';
            card.style.willChange = 'transform, filter';
            card.style.transformOrigin = 'top center';
            card.style.backfaceVisibility = 'hidden';
            card.style.perspective = '1000px';
            card.style.webkitPerspective = '1000px';
            card.style.transform = 'translateZ(0)';
            card.style.webkitTransform = 'translateZ(0)';
        });
    }

    function scrollToPos(pos) {
        pos = Math.max(0, pos);
        if (lenis) {
            lenis.scrollTo(pos, { duration: 1.1, easing: t => 1 - Math.pow(1 - t, 3) });
        } else {
            scroller.scrollTo({ top: pos, behavior: 'smooth' });
        }
    }

    function topCardIndexAt(scrollTop) {
        let top = 0;
        for (let j = 0; j < cards.length; j++) {
            if (scrollTop >= pinStartOf(j)) top = j;
        }
        return top;
    }

    function setupAccordion() {
        const items = Array.from(scroller.querySelectorAll('.faq-item'));
        items.forEach(item => {
            const summary = item.querySelector('summary');
            if (!summary) return;
            summary.addEventListener('click', () => {
                setTimeout(() => {
                    const opened = item.open;
                    items.forEach(other => {
                        if (other !== item && other.open) other.open = false;
                    });

                    if (!opened) { sync(); return; }

                    setTimeout(() => {
                        const i = cards.indexOf(item);
                        if (i === -1) return;
                        if (topCardIndexAt(scroller.scrollTop) !== i) {
                            scrollToPos(pinStartOf(i));
                        }
                        sync();
                    }, 430);
                }, 20);
            });
        });
    }

    if (reduceMotion) {
        scroller.classList.add('reduce-motion');
        setupCards();
        return;
    }

    setupCards();
    setupAccordion();

    if (window.Lenis) {
        lenis = new Lenis({
            wrapper: scroller,
            content: inner,
            duration: 1.2,
            easing: t => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
            smoothWheel: true,
            touchMultiplier: 2,
            infinite: false,
            normalizeWheel: true,
            wheelMultiplier: 1,
            lerp: 0.1,
            syncTouch: true,
            syncTouchLerp: 0.075
        });
        lenis.on('scroll', update);
        const raf = time => {
            lenis.raf(time);
            rafId = requestAnimationFrame(raf);
        };
        rafId = requestAnimationFrame(raf);
    } else {
        scroller.addEventListener('scroll', update, { passive: true });
    }

    sync();

    window.addEventListener('resize', sync);

    window.addEventListener('beforeunload', () => {
        if (rafId) cancelAnimationFrame(rafId);
        if (lenis) lenis.destroy();
    });
})();

// ── Site preloader ───────────────────────────────────────────
// Shows the white loading screen with the spinning ring around
// the logo, then zooms it out and reveals the page on load.
(function() {
    const preloader = document.getElementById('sitePreloader');
    if (!preloader) return;

    let released = false;
    const release = () => {
        if (released) return;
        released = true;
        preloader.classList.add('is-loaded');
        document.body.classList.remove('preloader-lock');
        setTimeout(() => {
            if (preloader.parentNode) preloader.parentNode.removeChild(preloader);
        }, 900);
    };

    document.body.classList.add('preloader-lock');

    const finish = () => setTimeout(release, 400);

    if (document.readyState === 'complete') {
        finish();
    } else {
        window.addEventListener('load', finish);
    }

    // Safety net: never block the site longer than 4s.
    setTimeout(release, 4000);
})();


// ── Global Custom Confirm Modal ──────────────────────────────────────────────
// Usage: const confirmed = await kipaConfirm({ title, message, type, confirmText, cancelText })
// type: 'danger' | 'warning' | 'primary'  (default: 'danger')

(function () {
    // Build the modal HTML once and inject into body
    function ensureModal() {
        if (document.getElementById('kipa-confirm-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'kipa-confirm-overlay';
        overlay.className = 'kipa-modal-overlay';
        overlay.innerHTML = `
            <div class="kipa-modal" role="dialog" aria-modal="true">
                <div class="kipa-modal-icon danger" id="kipa-modal-icon"></div>
                <h3 id="kipa-modal-title">Are you sure?</h3>
                <p id="kipa-modal-message">This action cannot be undone.</p>
                <div class="kipa-modal-actions">
                    <button type="button" class="btn-modal-cancel" id="kipa-modal-cancel">Cancel</button>
                    <button type="button" class="btn-modal-confirm danger" id="kipa-modal-confirm">
                        <span id="kipa-modal-confirm-text">Delete</span>
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        // Close on overlay backdrop click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) _resolveModal(false);
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('active')) _resolveModal(false);
        });

        document.getElementById('kipa-modal-cancel').addEventListener('click', () => _resolveModal(false));
        document.getElementById('kipa-modal-confirm').addEventListener('click', () => _resolveModal(true));
    }

    let _resolveFn = null;

    function _resolveModal(value) {
        const overlay = document.getElementById('kipa-confirm-overlay');
        if (!overlay) return;
        overlay.classList.remove('active');
        if (_resolveFn) { _resolveFn(value); _resolveFn = null; }
    }

    const ICON_MAP = {
        danger: {
            svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>`,
            btnClass: 'danger'
        },
        warning: {
            svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
            btnClass: 'warning'
        },
        primary: {
            svg: `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
            btnClass: 'primary'
        }
    };

    window.kipaConfirm = function ({ title = 'Are you sure?', message = 'This action cannot be undone.', type = 'danger', confirmText = 'Delete', cancelText = 'Cancel' } = {}) {
        ensureModal();

        const overlay      = document.getElementById('kipa-confirm-overlay');
        const iconWrap     = document.getElementById('kipa-modal-icon');
        const titleEl      = document.getElementById('kipa-modal-title');
        const msgEl        = document.getElementById('kipa-modal-message');
        const confirmBtn   = document.getElementById('kipa-modal-confirm');
        const confirmText2 = document.getElementById('kipa-modal-confirm-text');
        const cancelBtn    = document.getElementById('kipa-modal-cancel');

        const cfg = ICON_MAP[type] || ICON_MAP.danger;

        // Update content & icons
        iconWrap.className = `kipa-modal-icon ${cfg.btnClass}`;
        iconWrap.innerHTML = cfg.svg;
        titleEl.textContent = title;
        msgEl.innerHTML     = message;
        confirmBtn.className = `btn-modal-confirm ${cfg.btnClass}`;
        confirmText2.textContent = confirmText;
        cancelBtn.textContent    = cancelText;

        overlay.classList.add('active');
        setTimeout(() => cancelBtn.focus(), 80);

        return new Promise((resolve) => { _resolveFn = resolve; });
    };
})();
