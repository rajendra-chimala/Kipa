/**
 * upload.js – Handles the photo upload page
 * Features: Drag & drop, file previews, upload progress, results display
 */

// ── Toast helper (inline so page works standalone) ──────────────────────
function toast(msg, type = 'info') {
    let c = document.querySelector('.toast-container');
    if (!c) { c = document.createElement('div'); c.className = 'toast-container'; document.body.appendChild(c); }
    const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.innerHTML = `<span class="toast-icon">${icons[type]}</span><span class="toast-msg">${msg}</span>`;
    c.appendChild(t);
    setTimeout(() => { t.classList.add('leaving'); setTimeout(() => t.remove(), 300); }, 4000);
}

// ── State ───────────────────────────────────────────────────────────────
let selectedFiles = [];

// ── DOM Elements ────────────────────────────────────────────────────────
const uploadZone     = document.getElementById('uploadZone');
const fileInput      = document.getElementById('fileInput');
const browseBtn      = document.getElementById('browseBtn');
const previewSection = document.getElementById('previewSection');
const previewGrid    = document.getElementById('previewGrid');
const fileCount      = document.getElementById('fileCount');
const clearBtn       = document.getElementById('clearBtn');
const uploadBtn      = document.getElementById('uploadBtn');
const progressSection= document.getElementById('progressSection');
const progressBar    = document.getElementById('progressBar');
const progressLabel  = document.getElementById('progressLabel');
const progressPct    = document.getElementById('progressPct');
const progressSub    = document.getElementById('progressSub');
const resultsSection = document.getElementById('resultsSection');
const resultsGrid    = document.getElementById('resultsGrid');
const uploadMoreBtn  = document.getElementById('uploadMoreBtn');

// ── Drag & Drop ─────────────────────────────────────────────────────────
uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', ()  => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    addFiles([...e.dataTransfer.files]);
});
uploadZone.addEventListener('click', (e) => {
    // Only trigger if not clicking the browse button itself
    if (e.target !== browseBtn) fileInput.click();
});
browseBtn.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });
fileInput.addEventListener('change', () => addFiles([...fileInput.files]));

// ── File Management ─────────────────────────────────────────────────────
function addFiles(newFiles) {
    const imageFiles = newFiles.filter(f => f.type.startsWith('image/'));
    if (imageFiles.length === 0) {
        toast('Please select image files only (JPG, PNG, WEBP).', 'warning');
        return;
    }

    // Avoid duplicates by name+size
    const existing = new Set(selectedFiles.map(f => f.name + f.size));
    const unique   = imageFiles.filter(f => !existing.has(f.name + f.size));

    selectedFiles.push(...unique);
    renderPreviews();
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderPreviews();
}

function renderPreviews() {
    previewGrid.innerHTML = '';
    fileCount.textContent = selectedFiles.length;

    if (selectedFiles.length === 0) {
        previewSection.style.display = 'none';
        return;
    }
    previewSection.style.display = 'block';

    selectedFiles.forEach((file, idx) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const item = document.createElement('div');
            item.className = 'preview-item';
            item.innerHTML = `
                <img src="${e.target.result}" alt="${file.name}" loading="lazy" />
                <div class="preview-item-name">${file.name}</div>
                <button class="preview-remove" data-idx="${idx}" title="Remove">✕</button>
            `;
            item.querySelector('.preview-remove').addEventListener('click', (ev) => {
                ev.stopPropagation();
                removeFile(Number(ev.currentTarget.dataset.idx));
            });
            previewGrid.appendChild(item);
        };
        reader.readAsDataURL(file);
    });
}

clearBtn.addEventListener('click', () => {
    selectedFiles = [];
    fileInput.value = '';
    renderPreviews();
});

// ── Upload ──────────────────────────────────────────────────────────────
uploadBtn.addEventListener('click', startUpload);

async function startUpload() {
    if (selectedFiles.length === 0) { toast('No files selected.', 'warning'); return; }

    // Show progress, hide other sections
    previewSection.style.display  = 'none';
    progressSection.style.display = 'block';
    resultsSection.style.display  = 'none';

    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('images', f));

    setProgress(10, 'Uploading images…', 'Sending files to server…');

    try {
        // Simulate incremental progress during upload
        let fakeProgress = 10;
        const progressive = setInterval(() => {
            if (fakeProgress < 85) { fakeProgress += 5; setProgress(fakeProgress, 'Processing faces…', 'AI is detecting and encoding faces…'); }
        }, 500);

        const response = await fetch('/api/upload', { method: 'POST', body: formData });
        clearInterval(progressive);

        if (!response.ok) throw new Error(`Server error: ${response.status}`);

        const data = await response.json();
        setProgress(100, 'Complete!', 'All images processed.');

        setTimeout(() => {
            progressSection.style.display = 'none';
            showResults(data.results || []);
        }, 600);

    } catch (err) {
        progressSection.style.display = 'none';
        previewSection.style.display  = 'block';
        toast(`Upload failed: ${err.message}`, 'error');
        console.error(err);
    }
}

function setProgress(pct, label, sub) {
    progressBar.style.width = pct + '%';
    progressLabel.textContent = label;
    progressPct.textContent   = pct + '%';
    progressSub.textContent   = sub;
}

// ── Results ─────────────────────────────────────────────────────────────
function showResults(results) {
    resultsSection.style.display = 'block';
    resultsGrid.innerHTML = '';

    let successCount = 0;
    let totalFaces   = 0;

    results.forEach(r => {
        const isSuccess = r.status === 'success';
        const isNoFace  = r.status === 'no face detected';
        if (isSuccess) { successCount++; totalFaces += r.faces || 0; }

        const icon  = isSuccess ? '✅' : isNoFace ? '⚠️' : '❌';
        const badge = isSuccess ? 'badge-success' : isNoFace ? 'badge-warning' : 'badge-error';
        const label = isSuccess ? `${r.faces} face${r.faces!==1?'s':''} detected` : r.status;

        const item = document.createElement('div');
        item.className = 'result-item';
        item.innerHTML = `
            <span class="result-status-icon">${icon}</span>
            <div class="result-info">
                <div class="result-filename">${r.file}</div>
                <div class="result-detail">${label}</div>
            </div>
            <span class="result-badge ${badge}">${isSuccess ? '✓ OK' : isNoFace ? 'No Face' : 'Error'}</span>
        `;
        resultsGrid.appendChild(item);
    });

    if (successCount > 0) {
        toast(`✅ ${successCount} photo${successCount!==1?'s':''} uploaded — ${totalFaces} face${totalFaces!==1?'s':''} indexed.`, 'success', 6000);
    } else {
        toast('No photos were successfully processed.', 'warning');
    }
}

uploadMoreBtn.addEventListener('click', () => {
    selectedFiles = [];
    fileInput.value = '';
    resultsSection.style.display  = 'none';
    previewSection.style.display  = 'none';
    progressSection.style.display = 'none';
    toast('Ready for another upload!', 'info');
});
