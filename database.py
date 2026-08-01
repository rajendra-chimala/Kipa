"""
database.py – SQLite database helpers
Handles creation, insertion, and querying of users, events, assignments, images, and face encodings.
"""

import sqlite3
import json
import numpy as np
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = 'database.db'


def get_connection():
    """Create and return a new SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


def init_db():
    """Create tables if they do not exist and seed the default super_admin."""
    conn = get_connection()
    
    # ─── Migration Check: Drop face_encodings if old schema exists ──────────
    with conn:
        cursor = conn.execute("PRAGMA table_info(face_encodings)")
        cols = [row['name'] for row in cursor.fetchall()]
    with conn:
        cursor = conn.execute("PRAGMA table_info(users)")
        u_cols = [row['name'] for row in cursor.fetchall()]
        if u_cols and 'name' not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN name TEXT DEFAULT ''")
            print("[DB] Migrated 'name' column into users table.")
        if u_cols and 'email' not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
            print("[DB] Migrated 'email' column into users table.")
        if u_cols and 'profile_pic' not in u_cols:
            conn.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT DEFAULT ''")
            print("[DB] Migrated 'profile_pic' column into users table.")

    with conn:
        # 1. Users Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                name          TEXT    DEFAULT '',
                email         TEXT    DEFAULT '',
                profile_pic   TEXT    DEFAULT '',
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL, -- 'super_admin', 'photographer', 'assistant'
                created_by    INTEGER DEFAULT NULL, -- referencing users(id) for assistants
                created_at    TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')

        # 2. Events Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT    NOT NULL,
                description       TEXT    DEFAULT '',
                created_by        INTEGER NOT NULL, -- photographer user ID
                status            TEXT    DEFAULT 'unpublished', -- 'published', 'unpublished'
                deactivation_date TEXT    DEFAULT NULL, -- YYYY-MM-DD
                download_limit    INTEGER DEFAULT 1,
                created_at        TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # 3. Event Assignments Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS event_assignments (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id       INTEGER NOT NULL,
                user_id        INTEGER NOT NULL, -- assistant user ID
                can_upload     INTEGER DEFAULT 0, -- 1 or 0
                can_delete     INTEGER DEFAULT 0, -- 1 or 0
                can_deactivate INTEGER DEFAULT 0, -- 1 or 0
                created_at     TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(event_id, user_id)
            )
        ''')

        # 4. Images Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id    INTEGER NOT NULL,
                image_path  TEXT    NOT NULL,
                uploaded_by INTEGER NOT NULL, -- user ID
                created_at  TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY(uploaded_by) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # 5. Face Encodings Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS face_encodings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id      INTEGER NOT NULL,
                face_encoding TEXT    NOT NULL, -- JSON-serialized list
                created_at    TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE
            )
        ''')

        # 6. Downloads Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id       INTEGER NOT NULL,
                session_token  TEXT    NOT NULL,
                download_count INTEGER DEFAULT 0,
                downloaded_at  TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE,
                UNIQUE(image_id, session_token)
            )
        ''')

    # Seed Default Super Admin if not exists
    with conn:
        admin_exists = conn.execute(
            "SELECT 1 FROM users WHERE role = 'super_admin'"
        ).fetchone()
        if not admin_exists:
            pw_hash = generate_password_hash("admin123")
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", pw_hash, "super_admin")
            )
            print("[DB] Default super_admin seeded (admin / admin123).")

    conn.close()
    print('[DB] Database initialised successfully.')


# ─── User Helper Functions ───────────────────────────────────────────────────

def create_user(username, password, role, created_by=None):
    """Create a new user with a hashed password."""
    pw_hash = generate_password_hash(password)
    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(
                'INSERT INTO users (username, password_hash, role, created_by) VALUES (?, ?, ?, ?)',
                (username, pw_hash, role, created_by)
            )
            user_id = cursor.lastrowid
        return {'success': True, 'user_id': user_id}
    except sqlite3.IntegrityError:
        return {'success': False, 'message': 'Username already exists.'}
    finally:
        conn.close()


def verify_user(username, password):
    """Verify credentials and return user dict if correct, else None."""
    conn = get_connection()
    row = conn.execute(
        'SELECT id, username, name, email, profile_pic, password_hash, role FROM users WHERE username = ?',
        (username,)
    ).fetchone()
    conn.close()

    if row and check_password_hash(row['password_hash'], password):
        return {
            'id': row['id'],
            'username': row['username'],
            'name': row['name'] if row['name'] is not None else '',
            'email': row['email'] if row['email'] is not None else '',
            'profile_pic': row['profile_pic'] if row['profile_pic'] is not None else '',
            'role': row['role']
        }
    return None


def get_user_by_id(user_id):
    """Fetch user by primary key."""
    conn = get_connection()
    row = conn.execute(
        'SELECT id, username, name, email, profile_pic, role, created_by, created_at FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def update_user_profile(user_id, name=None, email=None, username=None, current_password=None, new_password=None):
    """Update profile details (name, email, username, password) for a user."""
    conn = get_connection()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        conn.close()
        return {'success': False, 'message': 'User account not found.'}

    # If password update requested, verify current password
    if new_password and new_password.strip():
        if not current_password or not check_password_hash(row['password_hash'], current_password):
            conn.close()
            return {'success': False, 'message': 'Current password is incorrect.'}

    # If username is changing, check uniqueness
    if username and username.strip() and username.strip() != row['username']:
        existing = conn.execute('SELECT id FROM users WHERE username = ? AND id != ?', (username.strip(), user_id)).fetchone()
        if existing:
            conn.close()
            return {'success': False, 'message': 'Username is already taken by another account.'}

    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name.strip())
    if email is not None:
        updates.append("email = ?")
        params.append(email.strip())
    if username is not None and username.strip():
        updates.append("username = ?")
        params.append(username.strip())
    if new_password and new_password.strip():
        updates.append("password_hash = ?")
        params.append(generate_password_hash(new_password.strip()))

    if not updates:
        conn.close()
        return {'success': True, 'message': 'No changes detected.'}

    params.append(user_id)
    try:
        with conn:
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        
        updated = conn.execute('SELECT id, username, name, email, profile_pic, role FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        return {
            'success': True,
            'message': 'Profile updated successfully!',
            'user': dict(updated)
        }
    except Exception as e:
        conn.close()
        return {'success': False, 'message': f'Failed to update profile: {str(e)}'}


def update_user_profile_pic(user_id, profile_pic_path):
    """Save or clear a user's profile picture path."""
    conn = get_connection()
    with conn:
        conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (profile_pic_path or '', user_id))
    conn.close()
    return {'success': True, 'message': 'Profile picture updated.'}


def get_assistants_by_photographer(photographer_id):
    """Fetch all assistant users created by a specific photographer."""
    conn = get_connection()
    rows = conn.execute(
        'SELECT id, username, created_at FROM users WHERE created_by = ? AND role = "assistant"',
        (photographer_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Event Helper Functions ──────────────────────────────────────────────────

def create_event(name, description, created_by, status='unpublished', deactivation_date=None, download_limit=1):
    """Create a new event."""
    conn = get_connection()
    with conn:
        cursor = conn.execute(
            '''INSERT INTO events (name, description, created_by, status, deactivation_date, download_limit)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (name, description, created_by, status, deactivation_date, download_limit)
        )
        event_id = cursor.lastrowid
    conn.close()
    return event_id


def update_event(event_id, name=None, description=None, status=None, deactivation_date=None, download_limit=None):
    """Update event properties dynamically."""
    conn = get_connection()
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if deactivation_date is not None:
        # Store empty string as NULL
        val = deactivation_date if deactivation_date else None
        updates.append("deactivation_date = ?")
        params.append(val)
    if download_limit is not None:
        updates.append("download_limit = ?")
        params.append(int(download_limit))

    if not updates:
        conn.close()
        return

    params.append(event_id)
    with conn:
        conn.execute(
            f"UPDATE events SET {', '.join(updates)} WHERE id = ?",
            params
        )
    conn.close()


def delete_event(event_id):
    """Delete an event (cascades to its images, face encodings, downloads and assignments)."""
    conn = get_connection()
    try:
        with conn:
            conn.execute('DELETE FROM events WHERE id = ?', (event_id,))
        conn.close()
        return {'success': True, 'message': 'Event deleted successfully.'}
    except Exception as e:
        conn.close()
        return {'success': False, 'message': f'Failed to delete event: {str(e)}'}


def get_event_by_id(event_id):
    """Fetch a single event and its status (including auto deactivation status)."""
    conn = get_connection()
    row = conn.execute('''
        SELECT e.*, u.username as creator_name
        FROM events e
        JOIN users u ON e.created_by = u.id
        WHERE e.id = ?
    ''', (event_id,)).fetchone()
    conn.close()
    if not row:
        return None
    
    event = dict(row)
    # Check auto deactivation:
    # If deactivation_date is set and current date > deactivation_date, it is inactive
    event['is_expired'] = False
    if event['deactivation_date']:
        try:
            deact_date = datetime.strptime(event['deactivation_date'], '%Y-%m-%d').date()
            if datetime.now().date() > deact_date:
                event['is_expired'] = True
        except ValueError:
            pass
            
    # Active status requires published AND not expired
    event['is_active'] = (event['status'] == 'published') and not event['is_expired']
    return event


def get_events_by_photographer(photographer_id):
    """Fetch all events created by a photographer, with helper properties."""
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM events WHERE created_by = ? ORDER BY created_at DESC',
        (photographer_id,)
    ).fetchall()
    conn.close()
    
    events = []
    for r in rows:
        event = dict(r)
        event['is_expired'] = False
        if event['deactivation_date']:
            try:
                deact_date = datetime.strptime(event['deactivation_date'], '%Y-%m-%d').date()
                if datetime.now().date() > deact_date:
                    event['is_expired'] = True
            except ValueError:
                pass
        event['is_active'] = (event['status'] == 'published') and not event['is_expired']
        events.append(event)
    return events


def get_all_published_active_events():
    """Fetch all events that are published and not expired."""
    conn = get_connection()
    rows = conn.execute('''
        SELECT e.*, u.username as creator_name
        FROM events e
        JOIN users u ON e.created_by = u.id
        WHERE e.status = 'published' AND 
              (e.deactivation_date IS NULL OR e.deactivation_date = '' OR e.deactivation_date >= date('now'))
        ORDER BY e.created_at DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_events_with_creators():
    """Fetch all events in the system with creator details."""
    conn = get_connection()
    rows = conn.execute('''
        SELECT e.*, u.username as creator_name
        FROM events e
        JOIN users u ON e.created_by = u.id
        ORDER BY e.created_at DESC
    ''').fetchall()
    conn.close()
    
    events = []
    for r in rows:
        event = dict(r)
        event['is_expired'] = False
        if event['deactivation_date']:
            try:
                deact_date = datetime.strptime(event['deactivation_date'], '%Y-%m-%d').date()
                if datetime.now().date() > deact_date:
                    event['is_expired'] = True
            except ValueError:
                pass
        event['is_active'] = (event['status'] == 'published') and not event['is_expired']
        events.append(event)
    return events


# ─── Assignment Helper Functions ─────────────────────────────────────────────

def assign_assistant_to_event(event_id, user_id, can_upload, can_delete, can_deactivate):
    """Assign/update assistant permissions for an event."""
    conn = get_connection()
    with conn:
        conn.execute('''
            INSERT INTO event_assignments (event_id, user_id, can_upload, can_delete, can_deactivate)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(event_id, user_id) DO UPDATE SET
                can_upload = excluded.can_upload,
                can_delete = excluded.can_delete,
                can_deactivate = excluded.can_deactivate
        ''', (event_id, user_id, int(can_upload), int(can_delete), int(can_deactivate)))
    conn.close()


def remove_assistant_from_event(event_id, user_id):
    """Unassign an assistant from an event."""
    conn = get_connection()
    with conn:
        conn.execute(
            'DELETE FROM event_assignments WHERE event_id = ? AND user_id = ?',
            (event_id, user_id)
        )
    conn.close()


def get_assignments_by_event(event_id):
    """Get all assistants assigned to an event with their permissions."""
    conn = get_connection()
    rows = conn.execute('''
        SELECT ea.*, u.username
        FROM event_assignments ea
        JOIN users u ON ea.user_id = u.id
        WHERE ea.event_id = ?
    ''', (event_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_assigned_events_for_assistant(user_id):
    """Fetch events assigned to an assistant user."""
    conn = get_connection()
    rows = conn.execute('''
        SELECT e.*, ea.can_upload, ea.can_delete, ea.can_deactivate, u.username as creator_name
        FROM events e
        JOIN event_assignments ea ON e.id = ea.event_id
        JOIN users u ON e.created_by = u.id
        WHERE ea.user_id = ?
        ORDER BY e.created_at DESC
    ''', (user_id,)).fetchall()
    conn.close()
    
    events = []
    for r in rows:
        event = dict(r)
        event['is_expired'] = False
        if event['deactivation_date']:
            try:
                deact_date = datetime.strptime(event['deactivation_date'], '%Y-%m-%d').date()
                if datetime.now().date() > deact_date:
                    event['is_expired'] = True
            except ValueError:
                pass
        event['is_active'] = (event['status'] == 'published') and not event['is_expired']
        events.append(event)
    return events


def get_assistant_permissions_for_event(user_id, event_id):
    """Fetch specific permissions for an assistant on an event."""
    conn = get_connection()
    row = conn.execute('''
        SELECT can_upload, can_delete, can_deactivate
        FROM event_assignments
        WHERE user_id = ? AND event_id = ?
    ''', (user_id, event_id)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


# ─── Image Helper Functions ──────────────────────────────────────────────────

def save_image_record(event_id, image_path, uploaded_by):
    """Insert an image record and return its primary key."""
    conn = get_connection()
    with conn:
        cursor = conn.execute(
            'INSERT INTO images (event_id, image_path, uploaded_by) VALUES (?, ?, ?)',
            (event_id, image_path, uploaded_by)
        )
        image_id = cursor.lastrowid
    conn.close()
    return image_id


def delete_image_record(image_id):
    """Delete an image record from database (cascade deletes face_encodings & downloads)."""
    conn = get_connection()
    with conn:
        conn.execute('DELETE FROM images WHERE id = ?', (image_id,))
    conn.close()


def get_image_by_id(image_id):
    """Get single image details."""
    conn = get_connection()
    row = conn.execute('SELECT * FROM images WHERE id = ?', (image_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_images_by_event(event_id):
    """Fetch all images for an event."""
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM images WHERE event_id = ? ORDER BY created_at DESC',
        (event_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Face Encoding Helper Functions ──────────────────────────────────────────

def save_face_encoding(image_id: int, encoding: np.ndarray):
    """Insert a face encoding linked to an image ID."""
    encoding_json = json.dumps(encoding.tolist())
    conn = get_connection()
    with conn:
        conn.execute(
            'INSERT INTO face_encodings (image_id, face_encoding) VALUES (?, ?)',
            (image_id, encoding_json)
        )
    conn.close()


def get_face_encodings_by_event(event_id: int):
    """Retrieve all stored face encodings for a specific event."""
    conn = get_connection()
    rows = conn.execute('''
        SELECT fe.id, i.image_path, fe.face_encoding, i.id as image_id
        FROM face_encodings fe
        JOIN images i ON fe.image_id = i.id
        WHERE i.event_id = ?
    ''', (event_id,)).fetchall()
    conn.close()

    result = []
    for row in rows:
        encoding = np.array(json.loads(row['face_encoding']))
        # Match format expected by face matching utils: (fe_id, image_path, numpy_encoding, image_id)
        result.append((row['id'], row['image_path'], encoding, row['image_id']))
    return result


# ─── Download Tracker & Filter Helper Functions ──────────────────────────────

def track_download(image_id, session_token):
    """Record a download action, incrementing download count."""
    conn = get_connection()
    with conn:
        row = conn.execute(
            'SELECT download_count FROM downloads WHERE image_id = ? AND session_token = ?',
            (image_id, session_token)
        ).fetchone()
        if row:
            conn.execute('''
                UPDATE downloads 
                SET download_count = download_count + 1, downloaded_at = datetime('now')
                WHERE image_id = ? AND session_token = ?
            ''', (image_id, session_token))
        else:
            conn.execute('''
                INSERT INTO downloads (image_id, session_token, download_count)
                VALUES (?, ?, 1)
            ''', (image_id, session_token))
    conn.close()


def filter_downloaded_images(event_id, image_paths, session_token):
    """
    Given an event, a list of image paths, and a session token,
    return only those image paths where the download count is less than the event's download_limit.
    """
    if not image_paths:
        return []
    
    conn = get_connection()
    event = conn.execute('SELECT download_limit FROM events WHERE id = ?', (event_id,)).fetchone()
    if not event:
        conn.close()
        return []
    limit = event['download_limit']
    
    # Query download count for session for these paths
    placeholders = ','.join('?' * len(image_paths))
    query = f'''
        SELECT i.image_path, COALESCE(d.download_count, 0) as download_count
        FROM images i
        LEFT JOIN downloads d ON i.id = d.image_id AND d.session_token = ?
        WHERE i.event_id = ? AND i.image_path IN ({placeholders})
    '''
    rows = conn.execute(query, [session_token, event_id] + list(image_paths)).fetchall()
    conn.close()
    
    allowed_paths = []
    for row in rows:
        if row['download_count'] < limit:
            allowed_paths.append(row['image_path'])
    return allowed_paths


# ─── Analytics / Stats Helper Functions ───────────────────────────────────────

def get_global_stats():
    """Return platform-wide statistics for the super_admin dashboard."""
    conn = get_connection()
    total_photographers = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'photographer'").fetchone()[0]
    total_assistants = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'assistant'").fetchone()[0]
    total_users = total_photographers + total_assistants + 1  # include admin

    # Calculate active vs inactive events based on publish status and expiration
    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    
    active_events = conn.execute('''
        SELECT COUNT(*) FROM events
        WHERE status = 'published' AND 
              (deactivation_date IS NULL OR deactivation_date = '' OR deactivation_date >= date('now'))
    ''').fetchone()[0]
    
    inactive_events = total_events - active_events

    total_images = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    total_downloads = conn.execute("SELECT COALESCE(SUM(download_count), 0) FROM downloads").fetchone()[0]
    
    conn.close()
    return {
        'total_users': total_users,
        'total_events': total_events,
        'active_events': active_events,
        'inactive_events': inactive_events,
        'total_images': total_images,
        'total_downloads': total_downloads
    }


def get_photographer_stats(photographer_id):
    """Return dashboard statistics for a specific photographer."""
    conn = get_connection()
    total_events = conn.execute("SELECT COUNT(*) FROM events WHERE created_by = ?", (photographer_id,)).fetchone()[0]
    
    active_events = conn.execute('''
        SELECT COUNT(*) FROM events
        WHERE created_by = ? AND status = 'published' AND 
              (deactivation_date IS NULL OR deactivation_date = '' OR deactivation_date >= date('now'))
    ''', (photographer_id,)).fetchone()[0]
    
    inactive_events = total_events - active_events
    
    total_images = conn.execute('''
        SELECT COUNT(*) FROM images i
        JOIN events e ON i.event_id = e.id
        WHERE e.created_by = ?
    ''', (photographer_id,)).fetchone()[0]
    
    total_downloads = conn.execute('''
        SELECT COALESCE(SUM(d.download_count), 0)
        FROM downloads d
        JOIN images i ON d.image_id = i.id
        JOIN events e ON i.event_id = e.id
        WHERE e.created_by = ?
    ''', (photographer_id,)).fetchone()[0]
    
    conn.close()
    return {
        'total_events': total_events,
        'active_events': active_events,
        'inactive_events': inactive_events,
        'total_images': total_images,
        'total_downloads': total_downloads
    }


def get_photographer_daily_downloads(photographer_id, days=30):
    """
    Return daily download counts for the last `days` days for a specific photographer.
    Returns a list of dicts: [{'date': 'YYYY-MM-DD', 'downloads': N}, ...]
    ordered from oldest to newest.
    """
    from datetime import date, timedelta

    conn = get_connection()
    # Use f-string for the days modifier — `days` is already an integer clamped by the API
    rows = conn.execute(f'''
        SELECT date(d.downloaded_at) AS day,
               COALESCE(SUM(d.download_count), 0) AS downloads
        FROM downloads d
        JOIN images i ON d.image_id = i.id
        JOIN events e  ON i.event_id = e.id
        WHERE e.created_by = ?
          AND date(d.downloaded_at) >= date('now', '-{days} days')
        GROUP BY day
        ORDER BY day ASC
    ''', (photographer_id,)).fetchall()
    conn.close()

    # Build a full date series filling 0 for days with no downloads
    result_map = {row['day']: int(row['downloads']) for row in rows}
    today = date.today()
    full_series = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        full_series.append({'date': d, 'downloads': result_map.get(d, 0)})
    return full_series


def get_photographer_event_chart_data(photographer_id):
    """
    Return per-event statistics for a photographer's overview pie/bar charts.
    Each row: id, name, is_active, total_images, total_downloads
    """
    from datetime import date as _date
    conn = get_connection()
    rows = conn.execute('''
        SELECT
            e.id,
            e.name,
            e.status,
            e.deactivation_date,
            COUNT(DISTINCT i.id)              AS total_images,
            COALESCE(SUM(d.download_count),0) AS total_downloads
        FROM events e
        LEFT JOIN images   i ON i.event_id  = e.id
        LEFT JOIN downloads d ON d.image_id = i.id
        WHERE e.created_by = ?
        GROUP BY e.id
        ORDER BY e.name ASC
    ''', (photographer_id,)).fetchall()
    conn.close()

    today = _date.today().isoformat()
    result = []
    for row in rows:
        is_active = (
            row['status'] == 'published' and
            (not row['deactivation_date'] or row['deactivation_date'] >= today)
        )
        result.append({
            'id':              row['id'],
            'name':            row['name'],
            'is_active':       is_active,
            'total_images':    int(row['total_images']),
            'total_downloads': int(row['total_downloads']),
        })
    return result


def get_all_users_with_creators():
    """Retrieve all users with their creator names (if any)."""
    conn = get_connection()
    rows = conn.execute('''
        SELECT u.id, u.username, u.name, u.email, u.profile_pic, u.role, u.created_at, creator.username as creator_name
        FROM users u
        LEFT JOIN users creator ON u.created_by = creator.id
        ORDER BY u.role, u.username
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_user(user_id, name=None, email=None, username=None, role=None, new_password=None):
    """Update user details (name, email, username, role, password) for admin management."""
    conn = get_connection()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        conn.close()
        return {'success': False, 'message': 'User account not found.'}

    # If username is changing, check uniqueness
    if username and username.strip() and username.strip() != row['username']:
        existing = conn.execute(
            'SELECT id FROM users WHERE username = ? AND id != ?',
            (username.strip(), user_id)
        ).fetchone()
        if existing:
            conn.close()
            return {'success': False, 'message': 'Username is already taken by another account.'}

    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name.strip())
    if email is not None:
        updates.append("email = ?")
        params.append(email.strip())
    if username is not None and username.strip():
        updates.append("username = ?")
        params.append(username.strip())
    if role is not None and role in ('super_admin', 'photographer', 'assistant'):
        updates.append("role = ?")
        params.append(role)
    if new_password and new_password.strip():
        updates.append("password_hash = ?")
        params.append(generate_password_hash(new_password.strip()))

    if not updates:
        conn.close()
        return {'success': True, 'message': 'No changes detected.'}

    params.append(user_id)
    try:
        with conn:
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.close()
        return {'success': True, 'message': 'User updated successfully!'}
    except Exception as e:
        conn.close()
        return {'success': False, 'message': f'Failed to update user: {str(e)}'}


def delete_user(user_id):
    """Delete a user account (cascades to their events, assignments, images and downloads)."""
    conn = get_connection()
    try:
        with conn:
            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.close()
        return {'success': True, 'message': 'User deleted successfully.'}
    except Exception as e:
        conn.close()
        return {'success': False, 'message': f'Failed to delete user: {str(e)}'}
