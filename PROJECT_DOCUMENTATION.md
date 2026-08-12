# KIPA – Face Recognition Photo Distribution System

**Full Technical Documentation & Interview Preparation Guide**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture](#3-system-architecture)
4. [Directory Structure](#4-directory-structure)
5. [Database Design](#5-database-design)
6. [User Roles & Access Control](#6-user-roles--access-control)
7. [Core Workflows](#7-core-workflows)
8. [Face Recognition Engine](#8-face-recognition-engine)
9. [Liveness & Anti-Spoofing System](#9-liveness--anti-spoofing-system)
10. [Download Limit & Tracking System](#10-download-limit--tracking-system)
11. [Authentication & Session Management](#11-authentication--session-management)
12. [Security Measures](#12-security-measures)
13. [API Reference](#13-api-reference)
14. [Frontend Architecture](#14-frontend-architecture)
15. [Analytics & Dashboards](#15-analytics--dashboards)
16. [File Storage Strategy](#16-file-storage-strategy)
17. [Key Algorithms & Techniques](#17-key-algorithms--techniques)
18. [Known Limitations & Future Improvements](#18-known-limitations--future-improvements)
19. [Interview Questions & Answers](#19-interview-questions--answers)
20. [SQLite → PostgreSQL Migration Guide](#20-sqlite--postgresql-migration-guide)

---

## 1. Project Overview

**KIPA** is a web-based, AI-powered photo distribution platform built for photographers. The core problem it solves: **photographers shoot hundreds of photos at events (weddings, concerts, festivals) and need a privacy-friendly way to let guests find and download *only their own* photos** — without exposing the entire gallery publicly.

Visitors use their **webcam to scan their face**, the system matches it against faces pre-indexed in the event's uploaded photos, and shows **only the matched photos** which they can download — subject to a **per-event download limit** and a **liveness/anti-spoof check** that prevents people from using a photo of someone else (or a printed photo / phone screen) to steal someone's photos.

The system has **3 internal user roles** (Super Admin, Photographer, Assistant) and **1 public visitor role** (guest scanning).

### Key Features
- Face recognition photo matching (128-d facial encodings, HOG-based detection)
- Multi-step **liveness / anti-spoofing** verification (mouth-open + blink challenges)
- Server-side verified liveness tokens (prevents API bypass)
- Per-photo-per-visitor **download limits** tracked by anonymous session tokens
- Event management with **auto-expiry (deactivation dates)**
- Assistant sub-user system with **granular permissions** (upload / delete / deactivate)
- Rich analytics dashboards (Chart.js) for photographers and super admin
- RBAC (role-based access control) across 3 roles
- Password-hashed authentication (Werkzeug / PBKDF2-SHA256)

---

## 2. Technology Stack

### Backend
| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.x | Core language |
| **Flask** | 3.0.3 | Web framework (routes, templating, sessions) |
| **Werkzeug** | 3.0.3 | WSGI utility library, password hashing, `secure_filename` |
| **SQLite** | Built-in | Relational database (embedded, zero-config) |
| **face-recognition** | 1.3.0 | Face detection, encoding, and matching (wraps dlib) |
| **dlib** | (dep) | C++ ML library: HOG face detection, 68-point landmarks, CNN encodings |
| **OpenCV (opencv-python)** | 4.9.0.80 | Image preprocessing, spoof analysis, frame scaling |
| **NumPy** | 1.26.4 | Vector math for encodings, distance calc, EAR/MAR computations |
| **Threading** | stdlib | Thread-safe in-memory liveness token store |

> **Note:** `face-recognition` internally depends on **dlib** and a pre-trained model that produces a **128-dimensional face embedding**. OpenCV is used for the anti-spoof heuristics and for scaling images before detection to speed up processing.

### Frontend
| Technology | Purpose |
|---|---|
| **HTML5** | Page structure (Jinja2 templating) |
| **CSS3** (custom `style.css`) | Design system, animations, dashboards |
| **Tailwind CSS** (CDN, browser build v4) | Used in photographer dashboard |
| **Font Awesome 6.7.2** | Icon library |
| **Google Fonts – Plus Jakarta Sans** | Typography |
| **Chart.js 4.4.3** | Interactive analytics charts |
| **Vanilla JavaScript** | All interactivity — no framework |
| **WebRTC (`getUserMedia`)** | Camera access for face scanning |
| **Canvas API** | Frame capture from webcam video |
| **IntersectionObserver** | Scroll-reveal animations, lazy counters |
| **sessionStorage / localStorage** | Temporary matched-results storage, visitor session token |
| **Lenis** (optional, if loaded) | Smooth scroll library for FAQ stack |
| **Jinja2** | Server-side templating, template inheritance, partials |

### Data Flow Summary
```
Browser (WebRTC camera) → Canvas capture → base64 JPEG → Flask JSON API
  → OpenCV/dlib/face-recognition processing → SQLite storage/query → JSON response → Browser gallery
```

---

## 3. System Architecture

The application follows a **monolithic Flask app** with a clear **Model-less / function-based data layer** separation:

```
┌─────────────────────────────────────────────────────────────────┐
│                      BROWSER (Client)                           │
│  Frontend templates + vanilla JS + WebRTC + Chart.js           │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP / JSON / Form-data
┌──────────────────────────────▼──────────────────────────────────┐
│                      Flask App (app.py)                         │
│  • Page routes        (render_template)                         │
│  • API routes         (JSON endpoints)                          │
│  • Decorators         login_required, role_required            │
│  • Liveness store     (in-memory thread-safe dict)             │
│  • File handling      (secure_filename, unique names)          │
└──────┬───────────────────────────────┬──────────────────────────┘
       │                               │
       │  utils/face_utils.py          │  database.py
       │  • face detection/encoding    │  • all SQLite operations
       │  • matching (distance)        │  • schema init + migrations
       │  • spoof analysis (OpenCV)    │  • stats queries
       │  • mouth ratio, EAR, base64   │
       ▼                               ▼
┌──────────────────┐      ┌───────────────────────────────┐
│  dlib + OpenCV   │      │   SQLite (database.db)        │
│  ML models       │      │   6 tables + foreign keys     │
└──────────────────┘      └───────────────────────────────┘
```

**Key design decision:** All `face_recognition` / OpenCV calls are **centralized in `utils/face_utils.py`** to keep `app.py` clean and the AI logic reusable/testable.

---

## 4. Directory Structure

```
Kipa/
├── app.py                      # Main Flask application (all routes + APIs)
├── database.py                 # SQLite helpers, schema, migrations, queries
├── database.db                 # SQLite database file (generated)
├── requirements.txt            # Python dependencies
├── static/
│   ├── css/style.css           # Full design system (site + dashboards)
│   ├── js/
│   │   ├── main.js             # Shared: toasts, scroll effects, counters, FAQ stack, preloader
│   │   ├── scan.js             # Webcam + face scan (legacy flow)
│   │   ├── upload.js           # Drag & drop upload page logic
│   │   └── gallery.js          # Matched-photo gallery + lightbox + download all
│   ├── images/                 # logo.png, marketing assets
│   ├── Image-Slider/           # Homepage slider images
│   ├── team/                   # Team photos
│   ├── favicon/                # Multi-size favicons + manifest
│   └── uploads/                # All user uploads
│       ├── <event_id>/         # Per-event photo folders (+ cover_image)
│       └── profile_pics/       # User avatar uploads
├── templates/
│   ├── frontend/               # Public marketing + event pages
│   │   ├── index.html, about.html, features.html, pricing.html
│   │   ├── events.html, event_detail.html, gallery.html
│   │   ├── auth.html, upload.html, scan.html
│   │   └── partials/           # navbar, footer, preloader, favicons
│   ├── photographer/dashboard.html
│   ├── assistant/assistant_dashboard.html
│   └── super_admin/super_admin.html
└── utils/
    ├── __init__.py
    └── face_utils.py           # All AI / image-processing helpers
```

---

## 5. Database Design

SQLite database with **foreign keys enabled** (`PRAGMA foreign_keys = ON` per connection). Six tables:

### 5.1 `users`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `username` | TEXT UNIQUE NOT NULL | |
| `name` | TEXT DEFAULT '' | Migrated in later |
| `email` | TEXT DEFAULT '' | Migrated in later |
| `profile_pic` | TEXT DEFAULT '' | Path to stored avatar |
| `password_hash` | TEXT NOT NULL | Werkzeug PBKDF2-SHA256 hash |
| `role` | TEXT NOT NULL | `super_admin` / `photographer` / `assistant` |
| `created_by` | INTEGER | FK → users(id) `ON DELETE SET NULL` — tracks who created an assistant |
| `created_at` | TEXT DEFAULT `datetime('now')` | |

### 5.2 `events`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT NOT NULL | |
| `description` | TEXT DEFAULT '' | |
| `created_by` | INTEGER NOT NULL | FK → users(id) `ON DELETE CASCADE` (photographer owner) |
| `status` | TEXT DEFAULT 'unpublished' | `published` / `unpublished` |
| `deactivation_date` | TEXT | YYYY-MM-DD, `NULL` = never expires |
| `download_limit` | INTEGER DEFAULT 1 | Max downloads per visitor per photo |
| `cover_image` | TEXT | Path to cover photo (migrated) |
| `created_at` | TEXT | |

### 5.3 `event_assignments`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `event_id` | INTEGER NOT NULL | FK → events ON DELETE CASCADE |
| `user_id` | INTEGER NOT NULL | FK → users ON DELETE CASCADE (assistant) |
| `can_upload` | INTEGER DEFAULT 0 | 0/1 permission |
| `can_delete` | INTEGER DEFAULT 0 | 0/1 permission |
| `can_deactivate` | INTEGER DEFAULT 0 | 0/1 permission |
| `created_at` | TEXT | |
| | | `UNIQUE(event_id, user_id)` — one row per pair |

### 5.4 `images`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `event_id` | INTEGER NOT NULL | FK → events ON DELETE CASCADE |
| `image_path` | TEXT NOT NULL | Relative path `static/uploads/<event>/file` |
| `uploaded_by` | INTEGER NOT NULL | FK → users ON DELETE CASCADE |
| `created_at` | TEXT | |

### 5.5 `face_encodings`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `image_id` | INTEGER NOT NULL | FK → images ON DELETE CASCADE |
| `face_encoding` | TEXT NOT NULL | **JSON-serialized 128-d float array** |
| `created_at` | TEXT | |

### 5.6 `downloads`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `image_id` | INTEGER NOT NULL | FK → images ON DELETE CASCADE |
| `session_token` | TEXT NOT NULL | Anonymous visitor identity |
| `download_count` | INTEGER DEFAULT 0 | Incremented per download |
| `downloaded_at` | TEXT | |
| | | `UNIQUE(image_id, session_token)` |

### Schema Migration Approach
Because this project grew organically, `init_db()` performs **ad-hoc migrations** using `PRAGMA table_info(...)` to detect missing columns and adds them via `ALTER TABLE` (e.g., `name`, `email`, `profile_pic`, `cover_image`). This is a lightweight alternative to Alembic.

### Cascade Behavior
`ON DELETE CASCADE` on `events→images→face_encodings/downloads` and `users→events` means deleting an event/user automatically removes dependent records. This is why `PRAGMA foreign_keys = ON` is **required on every connection**.

---

## 6. User Roles & Access Control

### 6.1 Roles
| Role | Created by | Capabilities |
|---|---|---|
| **super_admin** | Seeded automatically (`admin/admin123`) | Global dashboards, create/edit/delete any user, create events for any photographer |
| **photographer** | Registration / super admin | Full CRUD on own events, register assistants, assign permissions, upload/delete photos, stats |
| **assistant** | Photographer or super admin | View assigned events, upload/delete/deactivate **only if** granted |
| **guest** (unauthenticated) | — | Face-scan a public event, download matched photos within limit |

### 6.2 Implementation
Two decorators in `app.py`:

```python
def login_required(f):      # ensures 'user' in session + still exists in DB
def role_required(*roles):  # ensures session user's role ∈ roles
```

Both also perform a **DB existence check** (`get_user_by_id`) so stale sessions after DB resets are invalidated and the user is re-routed to login.

### 6.3 Super Admin Safeguards
- **Cannot change own role** (`user_id == session id` → role forced to `None`).
- **Cannot demote/delete the last super admin** (counts `super_admin` rows before updating/deleting).

### 6.4 Assistant Permission Enforcement
On every photo/event API, the assistant's permissions are re-fetched from `event_assignments` and checked server-side:
- Upload API → requires `can_upload`
- Delete API → requires `can_delete`
- Update API → assistants may **only** change `status`, and only with `can_deactivate`

The UI also hides upload zone / delete buttons, but **security relies on the server checks**, not the UI.

---

## 7. Core Workflows

### 7.1 Public Visitor Flow (Face Scan)
```
1. Guest opens /event/<id> (event_detail.html)
2. Clicks "Enable Webcam" → getUserMedia() → live video
3. Clicks "Scan My Face" → liveness challenge starts
4. Neutral frame captured → 1.5s countdown → action frame captured
5. Both frames POST to /api/event/<id>/liveness
6. Server verifies: mouth-open action + same-face + no spoof → marks session_token verified (in-memory, one-time)
7. Match frame POST to /api/event/<id>/match with session_token
8. Server: consumes liveness token, extracts face encoding, compares against event's stored encodings
9. Applies download-limit filter → returns only eligible matched photos
10. Renders matched photos with Download buttons
11. Each download hits /api/download/<id>?token=<token> → increments count, enforces limit
```

### 7.2 Photographer Flow
```
1. Register/Login → /dashboard
2. Create Event (+ optional cover image) → status "unpublished"
3. Upload photos (drag & drop or file picker) → faces indexed automatically
4. Publish event (sets status = published) → becomes visible on public site
5. Register Assistants → assign to events with permissions
6. View Overview: stat cards, daily downloads chart, pie/bar event charts
7. Optionally set deactivation_date → event auto-expires
```

### 7.3 Assistant Flow
```
1. Logged in → /assistant/dashboard
2. See only events assigned to them + their permissions
3. Can upload photos if can_upload; delete if can_delete; activate/deactivate if can_deactivate
```

### 7.4 Super Admin Flow
```
1. Login as seeded admin → /admin/dashboard
2. Global stats: users, events, images, downloads breakdowns
3. Create/edit/delete photographer & assistant accounts
4. Create events on behalf of photographers
```

---

## 8. Face Recognition Engine

### 8.1 Library & Model
Uses **`face-recognition`** (Python) which wraps **dlib**:
- **Detection:** HOG (Histogram of Oriented Gradients) + linear SVM classifier — CPU-friendly, fast.
- **Encoding:** dlib's ResNet-based 128-d embedding model.
- **Matching:** Euclidean `face_distance`; **distance ≤ 0.5** (configurable) = match.

### 8.2 Extraction (`extract_face_encodings`)
```python
image = face_recognition.load_image_file(image_path)     # RGB
face_locations = face_recognition.face_locations(image, model='hog')
encodings = face_recognition.face_encodings(image, known_face_locations=face_locations)
return encodings, len(encodings)
```
- Returns a **list of 128-d numpy arrays** — supports multi-face photos.
- Each encoding is stored as **JSON text** in `face_encodings` table (serialized via `json.dumps(enc.tolist())`).

### 8.3 Matching (`match_face_encoding`)
```python
distances = face_recognition.face_distance(known_encodings, user_encoding)
for idx, d in enumerate(distances):
    if d <= threshold: matched_ids.append(record_ids[idx])
```
- `threshold` default **0.5** (recommended by the library).
- Exposed in UI as a **sensitivity slider (30–70 → 0.30–0.70)**: strict (low) = fewer matches; relaxed (high) = more matches.

### 8.4 Performance Optimizations Used in Liveness
- Faces are detected on **0.5× scaled images** (via OpenCV resize), then coordinates are **multiplied back by 2** — roughly 4× faster detection with the HOG model.
- Landmarks & encodings are then computed on the **full-resolution image using the scaled-up locations** (accuracy preserved, detection sped up).

### 8.5 Storage vs. Computation Trade-off
The design chooses to **precompute and store encodings at upload time** (indexing) rather than recompute on every scan. This makes the scan-time query cheap: one encoding computation for the visitor + a bulk `face_distance` call.

---

## 9. Liveness & Anti-Spoofing System

This is the most advanced security feature. It prevents attackers from using a **printed photo**, **phone screen**, or **pre-recorded video** of someone else.

### 9.1 The Two-Frame Challenge
For each challenge, the client captures:
1. **`frame_neutral`** — resting face (before the countdown finishes)
2. **`frame_action`** — face during the requested action

Both are base64 JPEG data-URLs decoded server-side with `decode_base64_image`.

### 9.2 Challenges Implemented

**Mouth-open challenge** — uses the *Mouth Aspect Ratio (MAR)-like* metric `get_mouth_open_ratio`:
```
ratio = mouth_distance / eye_distance
       = ||top_lip_center − bottom_lip_center|| / ||left_eye_center − right_eye_center||
```
Pass condition: `ratio_action ≥ 0.12` **and** `ratio_action ≥ ratio_neutral × 1.8` (a relative increase of 80%).

**Blink challenge** — uses the *Eye Aspect Ratio (EAR)*:
```
EAR = (||p1−p5|| + ||p2−p4||) / (2·||p0−p3||)
```
Pass condition: `EAR_action ≤ 0.20` **or** `EAR_neutral − EAR_action ≥ 0.08` (eyes closed significantly relative to neutral).

These ratios are **scale-invariant** (normalized by eye distance) so they work at any camera distance.

### 9.3 Same-Face Cross-Check
`verify_same_face(enc_neutral, enc_action)` ensures both frames belong to the **same person** — blocking an attacker who changes who is in front of the camera mid-challenge.

### 9.4 Spoof Analysis (`analyze_spoof`) — OpenCV heuristics
| Signal | Method | Risk rule |
|---|---|---|
| Focus sharpness | **Laplacian variance** | `< 20` too smooth (printed photo) → +0.4; `> 500` too sharp (screen) → +0.2 |
| Edge density | **Canny edge detection**, ratio = edges/pixels | `> 0.18` screen noise → +0.35; `< 0.01` too smooth → +0.1 |
| Color flatness | **Histogram std-dev** | `< 500` flat (print) → +0.25 |
| Glare | % pixels `> 240` brightness | `> 5%` screen glare → +0.2 |

Combined risk = `min(1.0, sum)`. A scan is rejected if `risk ≥ 0.5`, returning a flag like `spoof_suspected`.

### 9.5 Server-Side Verification Store (anti-API-bypass)
A **thread-safe in-memory store** (dict + `threading.Lock`) maps:
```
session_token → { 'verified': True, 'encoding': np.ndarray }
```
- `/api/.../liveness` **marks** the token verified.
- `/api/.../match` **consumes** it (one-time `pop`) — a match request without a verified token returns **403**.
- This means clients **cannot simply set a `liveness=true` flag**; the server proves liveness itself.
- Tokens are stored per browser via `localStorage` (`facesnap_session_token`).
- Note: the store is in-memory and lost on restart — a known limitation (see §18).

### 9.6 Why Liveness Matters
Without it, anyone could hold up a printed photo of the victim, scan it, and download the victim's private photos. The challenge design makes photos/screens detectable and requires a **real, moving human face**.

---

## 10. Download Limit & Tracking System

### 10.1 Model
Each event defines a `download_limit` (default 1). Each visitor (identified by an **anonymous session token**) can download each photo at most `limit` times.

### 10.2 Enforcement Points (both server-side)
1. **Filtering at match time** — `filter_downloaded_images()`:
   - LEFT JOINs `downloads` for the visitor's `session_token`
   - Returns only image paths where `download_count < limit`
   - Already-exhausted photos simply don't appear in results.
2. **Hard check at download time** — `/api/download/<id>?token=...`:
   - Re-reads current count; returns **403 "Download limit reached"** if `count >= limit`.
   - Otherwise `track_download()` increments (INSERT ... or UPDATE ...), then streams file via `send_from_directory(..., as_attachment=True)`.

### 10.3 Implementation Detail — `track_download`
Uses an upsert pattern:
```sql
SELECT download_count FROM downloads WHERE image_id=? AND session_token=?;
-- if exists: UPDATE ... SET download_count = download_count + 1
-- else:     INSERT ... (download_count=1)
```
With `UNIQUE(image_id, session_token)` guaranteeing one row per visitor-photo pair.

---

## 11. Authentication & Session Management

### 11.1 Signup / Login
- **Registration** (`/api/register`): creates a `photographer` (public signup only for photographers).
- **Login** (`/api/login`): verifies with `check_password_hash`, stores user dict in Flask `session`, returns role-based redirect URL.
- **Password hashing:** Werkzeug `generate_password_hash` — **PBKDF2-SHA256 with a per-user salt** (never stored in plaintext).
- Sessions use Flask's **signed cookie** session (server-side secret key).

### 11.2 Session Invalidation Guards
- `login_required` / `role_required` re-check `get_user_by_id(session['user']['id'])` on every protected request — handles DB resets gracefully.

### 11.3 Session vs Token
- **Authenticated users** → Flask server-side session (`session['user']`).
- **Anonymous visitors** → client-generated random `session_token` persisted in `localStorage` (used for download limits + liveness).

### 11.4 Profile Updates
`/api/user/profile` handles name/email/username/password. If a new password is set, the **current password must be verified** first. Username uniqueness is checked excluding the current user.

---

## 12. Security Measures

| Concern | Mitigation |
|---|---|
| **Password storage** | Werkzeug PBKDF2-SHA256 hashing |
| **Path traversal / filenames** | `secure_filename()` + timestamp prefix + whitelist extension check |
| **Unauthorized access** | `role_required` + per-resource ownership checks (403s) |
| **Stale sessions** | DB-existence check inside decorators |
| **Liveness bypass** | Server-side verified one-time token store |
| **Download quota bypass** | Server-side re-check at download time (not just UI filtering) |
| **Upload abuse** | `MAX_CONTENT_LENGTH` 50 MB, allowed extensions only |
| **SQL injection** | Parameterized queries everywhere (`?` placeholders) |
| **XSS (templates)** | Jinja2 auto-escaping; JS-rendered content mostly sanitized by library usage |
| **Delete race conditions** | `send_from_directory` guarded by DB state check |
| **Spoofing photos** | Multi-signal OpenCV analysis |

> **Known gap:** `app.secret_key` is a hardcoded string in `app.py` — in production this should come from an environment variable.

---

## 13. API Reference

### Public (no auth)
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Home page |
| GET | `/about`, `/features`, `/pricing` | Marketing pages |
| GET | `/events` | All active published events |
| GET | `/event/<id>` | Event detail + webcam scan page |
| POST | `/api/register` | Create photographer |
| POST | `/api/login` | Login, returns role-based redirect |
| GET | `/logout` | Clear session |
| POST | `/api/event/<id>/liveness` | Two-frame anti-spoof challenge |
| POST | `/api/event/<id>/match` | Face match (requires verified liveness token) |
| GET | `/api/download/<image_id>` | Download (enforces limits via `?token=`) |
| GET | `/static/uploads/<path>` | Serve uploaded files |

### Authenticated User
| Method | Endpoint | Roles | Purpose |
|---|---|---|---|
| POST | `/api/user/profile` | any | Update profile |
| POST/DELETE | `/api/user/profile-pic` | any | Upload/remove avatar |

### Photographer + Super Admin
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/dashboard` | Photographer dashboard |
| GET | `/api/overview/downloads?days=N` | Daily download series |
| GET | `/api/overview/event-stats` | Per-event chart data |
| POST | `/api/event/create` | Create event |
| POST | `/api/event/<id>/update` | Update event config |
| POST | `/api/event/<id>/delete` | Delete event + files |
| POST | `/api/assistant/create` | Create assistant |
| POST | `/api/event/assign-assistant` | Assign perms |
| POST | `/api/event/remove-assistant` | Unassign |
| GET | `/api/event/<id>/assignments` | List assignments |
| GET | `/api/event/<id>/photos` | List event photos |
| POST | `/api/event/<id>/upload` | Bulk upload + auto-index |
| DELETE | `/api/event/<id>/image/<iid>` | Delete a photo |

### Super Admin Only
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/admin/dashboard` | Global dashboard |
| GET | `/api/admin/chart-stats` | Global chart JSON |
| POST | `/api/admin/user/create` | Create any account |
| POST | `/api/admin/user/update` | Edit user/role |
| POST | `/api/admin/user/delete` | Delete user |

**Response convention:** JSON `{success: bool, message?, data?, ...}` with appropriate HTTP status codes (400/401/403/404/500).

---

## 14. Frontend Architecture

### 14.1 Templating
Jinja2 with **partial includes**:
- `frontend/partials/navbar.html`, `footer.html`, `preloader.html`, `favicons.html`
- Dashboards are **standalone pages** (no base template) that share CSS classes from `style.css`.

### 14.2 Shared JS (main.js)
- **Toast notification system** (`Kipa.toast`)
- **Scroll-reveal** via IntersectionObserver (`.fade-up` elements)
- **Animated counters** (`.stat-count[data-target]`, ease-out cubic)
- **FAQ scroll-stack** — a custom vanilla-JS port of a React "ScrollStack" (pin/stack cards, optional Lenis smooth scroll)
- **Preloader** with 4s safety timeout

### 14.3 Scan Flow JS (event_detail.html inline)
- WebRTC `getUserMedia` with **mirror compensation** (`ctx.translate + scale(-1,1)` before drawImage)
- Frame captured to Canvas → `toDataURL('image/jpeg', 0.85)`
- Liveness panel with countdown bar, challenges, retry UI
- Matched-photo gallery rendering with download buttons + "fading-out" removal

### 14.4 Upload UX (upload.js / dashboard)
- Drag & drop zone, duplicate detection (name+size), FileReader previews
- Progressive fake-progress + per-file sequential upload with face-count reporting

### 14.5 Gallery (gallery.js)
- sessionStorage hand-off from scan page → gallery
- Lightbox with keyboard navigation (←/→/Esc), download all (staggered 300ms to avoid browser popup blocking)

### 14.6 Dashboards
- Photographer: stat cards + **Chart.js** line (daily downloads, period buttons 7/14/30d), pie (photos per event), bar (downloads per active event) + workflow guide cards
- Assistant: assigned-events table with permission badges, in-page settings
- Super admin: users/events/media breakdown charts (seeded in JS from `chart_data`)

---

## 15. Analytics & Dashboards

### Photographer Overview
- **Stat cards:** total events, active events, inactive events, uploaded photos, downloads.
- **Daily downloads chart:** 7/14/30-day toggle → `/api/overview/downloads?days=`.
- **Pie chart:** photos per event. **Bar chart:** downloads per active event → `/api/overview/event-stats`.

### Super Admin Overview
- **User roles breakdown** (photographers / assistants / admins).
- **Event status breakdown** (active / inactive / published / unpublished).
- **Media totals** (uploaded / downloaded).
- **14-day global download trend.**

### SQL Analytics Patterns Used
- `date(downloaded_at)`, `GROUP BY`, `COALESCE(SUM(...),0)`
- Building a **full date series in Python** to fill zeros for days without downloads (gaps in time-series charts).
- `LEFT JOIN` with `COUNT(DISTINCT)` to avoid double-counting when aggregating images + downloads per event.
- `date('now', '-N days')` for relative time windows.

---

## 16. File Storage Strategy

```
static/uploads/
├── <event_id>/                      # per-event gallery folder
│   ├── cover_<timestamp>.<ext>      # event cover image
│   └── <YYYYMMDD_HHMMSS_micro>_<secure_name>   # photos, unique names
└── profile_pics/
    └── user_<id>_<timestamp>_<secure_name>     # avatars
```

- **Unique naming:** timestamp (`%Y%m%d_%H%M%S_%f`) prefix + `secure_filename()` prevents collisions and path traversal.
- **Path normalization:** backslashes replaced with forward slashes before DB storage (`save_path.replace('\\','/')`) for cross-platform web serving.
- **Cover image flow:** event created first → cover saved under `<event_id>/` → `update_event(cover_image=...)`.
- **Delete cleanup:** events/photos remove both DB rows (cascade) **and** physical files (`os.remove`), plus orphan directory removal.
- **Temporary files:** liveness frames and scan queries written as `_lv_*` / `_tmp_scan_*` then deleted in `finally`/after use.

---

## 17. Key Algorithms & Techniques

1. **128-d Face Embedding Matching** — convert faces to vectors, compare by Euclidean distance, threshold at 0.5.
2. **Mouth Aspect Ratio (MAR)** — normalized mouth-opening metric, scale invariant.
3. **Eye Aspect Ratio (EAR)** — blink detection metric.
4. **Multi-signal Spoof Detection** — Laplacian variance + Canny edge ratio + histogram std + glare.
5. **Downscale-then-scale face detection** — detect on 0.5× frame for 4× speed, restore coordinates.
6. **Upsert** (`INSERT ... ON CONFLICT DO UPDATE`) for download tracking and assistant permissions.
7. **Full-series date filling** — pad missing days with zero for charts.
8. **One-time server-side token consumption** — `dict.pop()` guarantees single use.
9. **Ad-hoc schema migration** — `PRAGMA table_info` + `ALTER TABLE`.
10. **Defense-in-depth download limits** — filter at match time + hard-check at download time.

---

## 18. Known Limitations & Future Improvements

| Limitation | Suggested Improvement |
|---|---|
| In-memory liveness store lost on restart | Redis-backed store with TTL |
| `face-recognition`/dlib is heavy to install (requires C++/CMake) | Use ONNX/ONNXRuntime or a cloud face API (e.g., AWS Rekognition) |
| HOG detection struggles with small/rotated faces | Use dlib CNN detector or MTCNN/RetinaFace |
| Threshold tuning is manual | Auto-calibration per event or model confidence scores |
| No rate limiting | Flask-Limiter on scan/match/download endpoints |
| `secret_key` hardcoded | Environment variable / config file |
| No pagination on big galleries | Server-side pagination / lazy loading |
| No CSRF protection on POST forms | Flask-WTF CSRF extension |
| SQLite single-writer limitation | Migrate to PostgreSQL — see §20 |
| Emoji/legacy UI inconsistencies | Already partially fixed; unify with icon library |
| No tests | Add pytest + unit tests for `face_utils` and DB helpers |

---

## 19. Interview Questions & Answers

### General / Architecture
**Q: What is the project about?**
A: KIPA is a face-recognition-based photo distribution platform for photographers. At events, guests scan their face with a webcam; the system matches it against pre-indexed faces in the event's photos and only shows/downloads *their own* photos — with liveness/anti-spoof protection and per-photo download limits.

**Q: What is the tech stack?**
A: Python 3 + Flask 3 + SQLite + face-recognition (dlib) + OpenCV + NumPy on the backend; vanilla HTML/CSS/JS, WebRTC, Canvas, Chart.js, Tailwind (CDN), and Font Awesome on the frontend. Jinja2 for server-side templating.

**Q: How is the project structured?**
A: Monolithic Flask app. `app.py` holds all routes/APIs. `database.py` is a pure data-access layer with SQLite. `utils/face_utils.py` centralizes all AI/image code. `templates/` split into `frontend/` (public pages) and role-based dashboards. `static/` holds CSS, JS, and user uploads.

### Face Recognition
**Q: How does face matching work?**
A: At upload time, each photo's faces are detected with a HOG model and converted to 128-d embeddings (dlib ResNet). These are stored as JSON in SQLite. At scan time, the visitor's face is encoded the same way and compared to all event encodings using Euclidean distance via `face_recognition.face_distance`; distances ≤ 0.5 are matches.

**Q: Why store encodings instead of the images?**
A: Speed — indexing once at upload keeps the scan path O(1) per photo (bulk vector distance) instead of recomputing. Also lighter than storing image features.

**Q: How do you handle multiple faces in one photo?**
A: `extract_face_encodings` returns a list; one `face_encodings` row is saved per detected face, all linked to the same image. At match time the visitor's encoding is compared against every row.

### Liveness / Anti-Spoof
**Q: Why a liveness check?**
A: To prevent someone holding a printed photo or phone screen of another person from stealing their photos. The challenge proves a real human is present.

**Q: How do you detect a photo/screen?**
A: A combination of OpenCV signals: Laplacian variance (blur), Canny edge density, histogram flatness, and glare detection. Risks are summed; ≥0.5 rejects the scan.

**Q: How do you prevent API bypass?**
A: Liveness success marks a one-time server-side token (thread-safe in-memory store). The match endpoint consumes the token (`pop`), so a request without a server-verified token gets 403 regardless of client flags.

**Q: What are MAR and EAR?**
A: Mouth Aspect Ratio normalizes mouth opening by eye distance (scale-invariant). Eye Aspect Ratio measures eye openness; EAR drops sharply when blinking. Both are computed from dlib's 68 facial landmarks.

### Download Limits
**Q: How is the download limit enforced?**
A: Two layers: (1) at match time the results are filtered so already-exhausted photos don't appear; (2) at download time the count is re-read and a 403 is returned if the limit is hit, then `track_download` increments. Visitors are identified by an anonymous session token, so no login is required to limit downloads.

### Security
**Q: What security measures exist?**
A: PBKDF2 password hashing, parameterized SQL, `secure_filename` + extension whitelist, 50 MB upload cap, role-based decorators with ownership checks, stale-session invalidation, server-side liveness tokens, and server-side download-limit enforcement.

**Q: Any known gaps?**
A: The secret key is hardcoded, no CSRF protection, no rate limiting, in-memory liveness store resets on restart, and SQLite's single-writer constraint limits scale.

### Performance
**Q: What optimizations did you make for the face scan?**
A: Face detection runs on a 0.5× scaled frame (≈4× faster), coordinates are restored by ×2, and landmarks/encodings are computed at full resolution. Liveness analysis on two frames is done once and reuses the same locations.

### Role-Based Access
**Q: How do assistant permissions work?**
A: A `event_assignments` table with `can_upload`, `can_delete`, `can_deactivate` per (event, assistant) pair, enforced server-side on every API call. The UI only hides what the server would refuse anyway.

### Frontend
**Q: How does the webcam scanning work in the browser?**
A: WebRTC `getUserMedia` streams to a `<video>`. Frames are drawn to a hidden `<canvas>` (with horizontal mirror compensation), exported as base64 JPEG via `toDataURL`, and POSTed as JSON to the API.

**Q: How do matched results get to the gallery?**
A: Stored in `sessionStorage` (`matchedImages`) by the scan page and read by `gallery.js`, which renders a lightbox gallery with individual and "download all" buttons.

### Database
**Q: Describe the database schema.**
A: Six tables — `users`, `events`, `event_assignments`, `images`, `face_encodings`, `downloads` — linked by foreign keys with cascade deletes, and `UNIQUE` constraints for assignment pairs and download rows. Foreign keys are enabled per connection.

**Q: How did you handle schema changes over time?**
A: A lightweight migration step in `init_db()` inspects `PRAGMA table_info(...)` and adds missing columns with `ALTER TABLE`, avoiding a migration framework.

---

## 20. SQLite → PostgreSQL Migration Guide

This project currently stores everything in a single-file **SQLite** database (`database.db`) accessed directly through the built-in `sqlite3` module in `database.py`. PostgreSQL is the natural upgrade path for production (concurrent writers, better scalability, network access, role/row-level security).

Below is the full process, with **every SQLite-specific pattern in this codebase** called out and its PostgreSQL equivalent.

### 20.1 Step 1 — Install PostgreSQL & Python Driver

```bash
# Server (Windows): download installer from postgresql.org
# Then install the psycopg2 driver:
pip install psycopg2-binary        # or "psycopg2" if libpq is available
```

Add `psycopg2-binary==2.9.x` to `requirements.txt` (keep `numpy`, `Flask`, etc. unchanged).

### 20.2 Step 2 — Create Database & User

```sql
CREATE USER kipa_user WITH PASSWORD 'strong_password';
CREATE DATABASE kipa_db OWNER kipa_user ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE kipa_db TO kipa_user;
```

### 20.3 Step 3 — Central Connection Factory (minimal refactor)

The cleanest minimal change: keep `database.py` as a single data-access layer and swap the **connection factory** only, then fix the dialect differences.

```python
# Current (database.py):
DB_PATH = 'database.db'
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn
```

```python
# Target (PostgreSQL):
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = dict(
    dbname='kipa_db', user='kipa_user', password='strong_password',
    host='localhost', port=5432,
)

def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    return conn
```

> **Important difference:** `psycopg2` connections do **not** have an `.execute()` method — only cursors do. The current code calls `conn.execute(...)` in many places. You must introduce a **proxy connection** or change every call to use a cursor, e.g.:
>
> ```python
> class PGConn:
>     def __init__(self, conn): self.conn = conn
>     def execute(self, q, p=()):
>         cur = self.conn.cursor(cursor_factory=RealDictCursor)
>         cur.execute(q, p)
>         return cur
>     def close(self): self.conn.close()
>     def __enter__(self): return self.conn
>     def __exit__(self, *a): self.conn.commit() if not a[0] else self.conn.rollback()
> ```
>
> With `RealDictCursor`, `row['column']` access and `dict(row)` keep working exactly like `sqlite3.Row`.

### 20.4 Step 4 — SQL Dialect Differences (exact list for this codebase)

| # | SQLite pattern used | PostgreSQL equivalent | Where in code |
|---|---|---|---|
| 1 | `PRAGMA foreign_keys = ON` | Not needed — PG enforces FKs always | `get_connection()` |
| 2 | Placeholder `?` | `%s` | **every query** in `database.py` |
| 3 | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL` or `INTEGER GENERATED BY DEFAULT AS IDENTITY` | `init_db()` DDL |
| 4 | `DEFAULT (datetime('now'))` | `DEFAULT now()` | `init_db()` DDL |
| 5 | `conn.execute(...)` on connection | cursor-only → proxy wrapper (see 20.3) | `database.py`, `app.py` count queries |
| 6 | `cursor.lastrowid` | `RETURNING id` + `cursor.fetchone()[0]` | `create_user`, `create_event`, `save_image_record` |
| 7 | `date('now')` | `CURRENT_DATE` | `get_all_published_active_events`, `get_global_stats`, `get_global_chart_data`, `get_photographer_stats` |
| 8 | `date('now', '-{days} days')` | `CURRENT_DATE - {days}` (or `CURRENT_DATE - INTERVAL '{days} days'`) | `get_photographer_daily_downloads` |
| 9 | `date(downloaded_at)` | `downloads.downloaded_at::date` (or `date(downloaded_at)` — PG has it too) | `get_global_chart_data`, `get_photographer_daily_downloads` |
| 10 | `ON CONFLICT(event_id, user_id) DO UPDATE SET ... excluded.<col>` | **Identical syntax** (PG 9.5+) ✅ | `assign_assistant_to_event`, `track_download` |
| 11 | `INSERT INTO ... ; SELECT id, ... FROM users WHERE ...` fetch last inserted | Use `RETURNING` | after INSERTs |
| 12 | `PRAGMA table_info(table)` migrations | `SELECT column_name FROM information_schema.columns WHERE table_name = %s` | `init_db()` migration block |
| 13 | `ALTER TABLE users ADD COLUMN name TEXT DEFAULT ''` | Same syntax works (`ADD COLUMN IF NOT EXISTS` preferred) | `init_db()` |
| 14 | `INTEGER` 0/1 booleans | Same — keep `INTEGER` (or switch to `BOOLEAN`) | `event_assignments.can_*` |
| 15 | `sqlite3.IntegrityError` (duplicate username) | `psycopg2.errors.UniqueViolation` (from `psycopg2.IntegrityError`) | `create_user` |

### 20.5 Step 5 — Refactoring Examples

**a) Insert with `RETURNING` instead of `lastrowid`:**
```python
# before
cursor = conn.execute('INSERT INTO users (username, password_hash, role, created_by) VALUES (?,?,?,?)', ...)
user_id = cursor.lastrowid

# after
row = conn.execute('INSERT INTO users (username, password_hash, role, created_by) VALUES (%s,%s,%s,%s) RETURNING id', ...).fetchone()
user_id = row['id']
```

**b) `track_download` upsert (unchanged syntax, only placeholders):**
```python
INSERT INTO downloads (image_id, session_token, download_count)
VALUES (%s, %s, 1)
ON CONFLICT (image_id, session_token) DO UPDATE SET
    download_count = downloads.download_count + 1,   # PG: qualify with table name (SQLite uses excluded. here)
    downloaded_at  = now()
```

> PG allows both `excluded.<col>` and `<table>.<col>` for the update side; SQLite only supports `excluded.`. Since the current SQLite code already uses `excluded.`, it will run **unchanged** on PostgreSQL — just update the placeholders.

**c) Date filtering:**
```python
# before
WHERE date(d.downloaded_at) >= date('now', '-{days} days')
# after
WHERE d.downloaded_at::date >= CURRENT_DATE - %s
```

### 20.6 Step 6 — Migrate Existing Data

Option A — **pgloader** (recommended, automated):
```bash
pgloader database.db postgresql://kipa_user:strong_password@localhost/kipa_db
```

Option B — **manual dump/restore** (SQLite → CSV/JSON → PG COPY). A small Python script using `sqlite3` to read and `psycopg2` to insert, table by table:
```python
# pseudocode
src = sqlite3.connect('database.db'); src.row_factory = sqlite3.Row
dst = get_connection()
for table in ['users', 'events', 'event_assignments', 'images', 'face_encodings', 'downloads']:
    rows = src.execute(f'SELECT * FROM {table}').fetchall()
    cols = list(rows[0].keys()) if rows else []
    for r in rows:
        placeholders = ', '.join(['%s'] * len(cols))
        dst.execute(f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({placeholders})', tuple(r[c] for c in cols))
```
> Preserve order: `users` → `events` → `event_assignments` → `images` → `face_encodings` → `downloads` (respects foreign keys).

### 20.7 Step 7 — Update `init_db()` Schema

- Replace `CREATE TABLE IF NOT EXISTS ... AUTOINCREMENT` with `SERIAL` / `IDENTITY` versions.
- Replace `PRAGMA table_info(...)` migration checks with `information_schema.columns` queries.
- PostgreSQL has **no** `IF NOT EXISTS` for `ALTER TABLE ADD COLUMN` — use a guard query:
  ```sql
  DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='email') THEN
          ALTER TABLE users ADD COLUMN email TEXT DEFAULT '';
      END IF;
  END $$;
  ```

### 20.8 Step 8 — Config via Environment Variables (Recommended)

Move connection settings out of code:
```python
import os
DB_CONFIG = dict(
    dbname=os.environ.get('PGDATABASE', 'kipa_db'),
    user=os.environ.get('PGUSER', 'kipa_user'),
    password=os.environ.get('PGPASSWORD', ''),
    host=os.environ.get('PGHOST', 'localhost'),
    port=int(os.environ.get('PGPORT', '5432')),
)
```
This also fixes the hardcoded-secret concern noted in §12.

### 20.9 Step 9 — Test the Migration

1. Run the app → confirm `init_db()` runs without errors.
2. Seed-check: log in as `admin` (super admin).
3. Create an event, upload a photo with a face → confirm a `face_encodings` row is written.
4. Public flow: open `/event/<id>`, complete a liveness challenge, scan, download → confirm `downloads` row increments and limit is enforced.
5. Check dashboards + chart endpoints return data.
6. Verify cascade delete still works (delete an event → images/encodings/downloads gone).

### 20.10 Alternative — SQLAlchemy (Bigger Refactor, Cleaner Long-Term)

Instead of psycopg2 + proxy wrappers, rewrite `database.py` on **SQLAlchemy Core/ORM**:
- One dialect-agnostic layer (`sqlalchemy.create_engine()`), `?` vs `%s` handled automatically.
- `Column(Text, server_default=func.now())`, `Sequence`, etc. abstract the differences.
- Costs: rewrite all 40+ helper functions, learn SQLAlchemy idioms, and migrate the DDL to `MetaData`/migrations (Alembic).

### 20.11 Decision Guide
| Approach | Effort | Result |
|---|---|---|
| psycopg2 + proxy connection (Steps 3–9) | Medium | Minimal diff, two dialects to maintain mentally |
| SQLAlchemy Core/ORM + Alembic | High | One clean abstraction, future-proof, recommended for real production |
| Keep SQLite | None | Fine for demo/single-server; blocked by single-writer limitation |

---

*Document generated for the KIPA project. Core entry points: `app.py`, `database.py`, `utils/face_utils.py`.*
