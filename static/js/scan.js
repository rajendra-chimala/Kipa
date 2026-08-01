/**
 * scan.js – WebRTC camera + face scan logic
 * Captures a webcam frame, sends it to /api/match, then redirects to gallery
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
const startCameraBtn     = document.getElementById('startCameraBtn');
const captureBtn         = document.getElementById('captureBtn');
const stopCameraBtn      = document.getElementById('stopCameraBtn');
const videoFeed          = document.getElementById('videoFeed');
const captureCanvas      = document.getElementById('captureCanvas');
const scanOverlay        = document.getElementById('scanOverlay');
const stateIdle          = document.getElementById('stateIdle');
const stateProcessing    = document.getElementById('stateProcessing');
const sensitivityControl = document.getElementById('sensitivityControl');
const thresholdSlider    = document.getElementById('thresholdSlider');
const sensitivityValue   = document.getElementById('sensitivityValue');
const statusDot          = document.getElementById('statusDot');
const statusText         = document.getElementById('statusText');

let stream = null;

// ── Sensitivity Label Mapping ───────────────────────────────────────────
const sensitivityLabels = {
    30: 'Very Strict',
    35: 'Strict',
    40: 'Fairly Strict',
    45: 'Moderate',
    50: 'Balanced',
    55: 'Relaxed',
    60: 'Fairly Relaxed',
    65: 'Very Relaxed',
    70: 'Maximum'
};
thresholdSlider.addEventListener('input', () => {
    const val = parseInt(thresholdSlider.value);
    // Pick nearest label
    const keys = Object.keys(sensitivityLabels).map(Number).sort((a,b) => a-b);
    const nearest = keys.reduce((a,b) => Math.abs(b-val) < Math.abs(a-val) ? b : a);
    sensitivityValue.textContent = sensitivityLabels[nearest] || 'Balanced';
});

// ── Start Camera ────────────────────────────────────────────────────────
startCameraBtn.addEventListener('click', startCamera);

async function startCamera() {
    try {
        setStatus('Requesting camera access…', 'scanning');
        stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
            audio: false
        });

        videoFeed.srcObject = stream;
        videoFeed.style.display = 'block';
        stateIdle.style.display = 'none';
        scanOverlay.style.display = 'block';

        startCameraBtn.style.display = 'none';
        captureBtn.style.display     = 'inline-flex';
        stopCameraBtn.style.display  = 'inline-flex';
        sensitivityControl.style.display = 'block';

        setStatus('Camera active — position your face in the frame', 'active');
        toast('Camera started! Align your face and click Scan.', 'info');

    } catch (err) {
        let message = 'Could not access camera.';
        if (err.name === 'NotAllowedError')  message = 'Camera permission denied. Please allow access in your browser settings.';
        if (err.name === 'NotFoundError')    message = 'No camera found on this device.';
        if (err.name === 'NotReadableError') message = 'Camera is already in use by another application.';

        setStatus(message, 'error');
        toast(message, 'error');
        console.error('[Camera]', err);
    }
}

// ── Stop Camera ─────────────────────────────────────────────────────────
stopCameraBtn.addEventListener('click', stopCamera);

function stopCamera() {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    videoFeed.srcObject = null;
    videoFeed.style.display      = 'none';
    scanOverlay.style.display    = 'none';
    stateIdle.style.display      = 'flex';
    stateProcessing.style.display= 'none';

    startCameraBtn.style.display = 'inline-flex';
    captureBtn.style.display     = 'none';
    stopCameraBtn.style.display  = 'none';
    sensitivityControl.style.display = 'none';

    setStatus('Ready to scan', 'idle');
}

// ── Capture & Match ─────────────────────────────────────────────────────
captureBtn.addEventListener('click', captureAndMatch);

async function captureAndMatch() {
    if (!stream) { toast('Please start the camera first.', 'warning'); return; }

    // Capture frame to canvas
    const video  = videoFeed;
    const canvas = captureCanvas;
    canvas.width  = video.videoWidth  || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    // Mirror compensation (video is CSS-mirrored)
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const imageData = canvas.toDataURL('image/jpeg', 0.9);

    // Show processing state
    videoFeed.style.display       = 'none';
    scanOverlay.style.display     = 'none';
    stateProcessing.style.display = 'flex';
    captureBtn.disabled           = true;
    stopCameraBtn.disabled        = true;
    setStatus('Scanning your face…', 'scanning');

    const threshold = parseInt(thresholdSlider.value) / 100;  // convert e.g. 50 → 0.50

    try {
        const response = await fetch('/api/match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: imageData, threshold })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || 'Server error');
        }

        if (data.success) {
            // Store results in sessionStorage and redirect to gallery
            sessionStorage.setItem('matchedImages', JSON.stringify(data.images));
            sessionStorage.setItem('matchCount', data.count);
            setStatus(`Found ${data.count} photo${data.count !== 1 ? 's' : ''}! Redirecting…`, 'success');
            toast(`<i class="fa-solid fa-circle-check"></i> Found ${data.count} matching photo${data.count !== 1 ? 's' : ''}!`, 'success');
            setTimeout(() => { window.location.href = '/gallery'; }, 1000);
        } else {
            // No match – restore camera view
            restoreCameraView();
            setStatus(data.message || 'No match found.', 'error');
            toast(data.message || 'No matching photos found.', 'warning');
        }

    } catch (err) {
        restoreCameraView();
        setStatus('Match request failed. Please try again.', 'error');
        toast(`Error: ${err.message}`, 'error');
        console.error('[Scan]', err);
    }
}

function restoreCameraView() {
    stateProcessing.style.display = 'none';
    videoFeed.style.display       = 'block';
    scanOverlay.style.display     = 'block';
    captureBtn.disabled           = false;
    stopCameraBtn.disabled        = false;
    setStatus('Camera active — try scanning again', 'active');
}

// ── Status Helper ───────────────────────────────────────────────────────
function setStatus(text, type) {
    statusText.textContent = text;
    statusDot.className    = `status-dot ${type}`;
}
