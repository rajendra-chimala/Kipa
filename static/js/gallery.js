/**
 * gallery.js – Gallery page logic
 * Reads matched image paths from sessionStorage and renders the gallery
 * with lightbox, download, and download-all features.
 */

// ── Toast helper ────────────────────────────────────────────────────────
function toast(msg, type = 'info') {
    let c = document.querySelector('.toast-container');
    if (!c) { c = document.createElement('div'); c.className = 'toast-container'; document.body.appendChild(c); }
    const icons = { success: '<i class="fa-solid fa-circle-check"></i>', error: '<i class="fa-solid fa-circle-xmark"></i>', info: '<i class="fa-solid fa-circle-info"></i>', warning: '<i class="fa-solid fa-triangle-exclamation"></i>' };
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.innerHTML = `<span class="toast-icon">${icons[type]}</span><span class="toast-msg">${msg}</span>`;
    c.appendChild(t);
    setTimeout(() => { t.classList.add('leaving'); setTimeout(() => t.remove(), 300); }, 5000);
}

// ── DOM Elements ────────────────────────────────────────────────────────
const galleryLoading   = document.getElementById('galleryLoading');
const galleryEmpty     = document.getElementById('galleryEmpty');
const galleryNoSession = document.getElementById('galleryNoSession');
const galleryToolbar   = document.getElementById('galleryToolbar');
const galleryGrid      = document.getElementById('galleryGrid');
const photoCount       = document.getElementById('photoCount');
const gallerySubtitle  = document.getElementById('gallerySubtitle');
const downloadAllBtn   = document.getElementById('downloadAllBtn');

// ── Lightbox Elements ───────────────────────────────────────────────────
const lightbox         = document.getElementById('lightbox');
const lightboxOverlay  = document.getElementById('lightboxOverlay');
const lightboxImage    = document.getElementById('lightboxImage');
const lightboxClose    = document.getElementById('lightboxClose');
const lightboxPrev     = document.getElementById('lightboxPrev');
const lightboxNext     = document.getElementById('lightboxNext');
const lightboxCounter  = document.getElementById('lightboxCounter');
const lightboxDownload = document.getElementById('lightboxDownload');

let images = [];
let currentLightboxIdx = 0;

// ── Init ─────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
    const stored = sessionStorage.getItem('matchedImages');

    if (!stored) {
        galleryLoading.style.display   = 'none';
        galleryNoSession.style.display = 'block';
        return;
    }

    try {
        images = JSON.parse(stored);
    } catch {
        images = [];
    }

    galleryLoading.style.display = 'none';

    if (images.length === 0) {
        galleryEmpty.style.display = 'block';
        return;
    }

    // Update header
    const count = images.length;
    gallerySubtitle.textContent = `We found ${count} photo${count !== 1 ? 's' : ''} featuring you from the event.`;
    photoCount.textContent      = `${count} photo${count !== 1 ? 's' : ''} found`;

    // Show toolbar & grid
    galleryToolbar.style.display = 'flex';
    galleryGrid.style.display    = 'grid';

    renderGallery(images);
});

// ── Render Gallery ───────────────────────────────────────────────────────
function renderGallery(imgs) {
    galleryGrid.innerHTML = '';
    imgs.forEach((imgPath, idx) => {
        const item = document.createElement('div');
        item.className = 'gallery-item';
        item.dataset.idx = idx;

        // Extract filename for alt text
        const filename = imgPath.split('/').pop();

        item.innerHTML = `
            <img src="/${imgPath}" alt="${filename}" loading="lazy" />
            <div class="gallery-item-overlay">
                <a class="gallery-item-dl" href="/${imgPath}" download="${filename}">
                    ⬇ Download
                </a>
            </div>
        `;

        // Click on image area (not overlay) opens lightbox
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.gallery-item-dl')) {
                openLightbox(idx);
            }
        });

        // Stop anchor click from bubbling to lightbox
        item.querySelector('.gallery-item-dl').addEventListener('click', (e) => {
            e.stopPropagation();
        });

        galleryGrid.appendChild(item);
    });
}

// ── Lightbox ─────────────────────────────────────────────────────────────
function openLightbox(idx) {
    currentLightboxIdx = idx;
    updateLightbox();
    lightbox.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    lightbox.style.display = 'none';
    document.body.style.overflow = '';
}

function updateLightbox() {
    const imgPath = images[currentLightboxIdx];
    const filename = imgPath.split('/').pop();

    lightboxImage.src = '/' + imgPath;
    lightboxImage.alt = filename;
    lightboxCounter.textContent = `${currentLightboxIdx + 1} / ${images.length}`;
    lightboxDownload.href       = '/' + imgPath;
    lightboxDownload.setAttribute('download', filename);

    lightboxPrev.style.display = currentLightboxIdx > 0 ? 'flex' : 'none';
    lightboxNext.style.display = currentLightboxIdx < images.length - 1 ? 'flex' : 'none';
}

lightboxClose.addEventListener('click', closeLightbox);
lightboxOverlay.addEventListener('click', closeLightbox);
lightboxPrev.addEventListener('click', () => { currentLightboxIdx--; updateLightbox(); });
lightboxNext.addEventListener('click', () => { currentLightboxIdx++; updateLightbox(); });

// Keyboard navigation
document.addEventListener('keydown', (e) => {
    if (lightbox.style.display === 'none') return;
    if (e.key === 'Escape')      closeLightbox();
    if (e.key === 'ArrowLeft'  && currentLightboxIdx > 0)                     { currentLightboxIdx--; updateLightbox(); }
    if (e.key === 'ArrowRight' && currentLightboxIdx < images.length - 1)     { currentLightboxIdx++; updateLightbox(); }
});

// ── Download All ─────────────────────────────────────────────────────────
downloadAllBtn.addEventListener('click', downloadAll);

function downloadAll() {
    if (images.length === 0) return;

    toast(`Starting download of ${images.length} photo${images.length !== 1 ? 's' : ''}…`, 'info');

    // Download each image with a slight delay to avoid browser blocking
    images.forEach((imgPath, idx) => {
        setTimeout(() => {
            const a = document.createElement('a');
            a.href     = '/' + imgPath;
            a.download = imgPath.split('/').pop();
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }, idx * 300);
    });
}
