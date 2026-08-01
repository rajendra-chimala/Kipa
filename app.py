"""
Flask Face Recognition Photo Distribution System
Main application file - handles all routes and API endpoints
"""

import os
import base64
import json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, flash, abort
from werkzeug.utils import secure_filename

from utils.face_utils import (
    extract_face_encodings,
    match_face_encoding,
    decode_base64_image,
    get_mouth_open_ratio,
    get_face_encoding_from_image,
    verify_same_face,
    analyze_spoof
)
from database import (
    init_db,
    get_connection,
    create_user,
    verify_user,
    get_user_by_id,
    get_assistants_by_photographer,
    create_event,
    update_event,
    get_event_by_id,
    get_events_by_photographer,
    get_all_published_active_events,
    get_all_events_with_creators,
    assign_assistant_to_event,
    remove_assistant_from_event,
    get_assignments_by_event,
    get_assigned_events_for_assistant,
    get_assistant_permissions_for_event,
    save_image_record,
    delete_image_record,
    get_image_by_id,
    get_images_by_event,
    save_face_encoding,
    get_face_encodings_by_event,
    track_download,
    filter_downloaded_images,
    get_global_stats,
    get_photographer_stats,
    get_photographer_daily_downloads,
    get_photographer_event_chart_data,
    get_all_users_with_creators,
    update_user_profile,
    update_user_profile_pic,
    update_user,
    delete_user
)

# ─── App Configuration ───────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'super-secret-key-for-photographer-app-12345'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
PROFILE_PIC_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pics')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB max upload size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PIC_FOLDER, exist_ok=True)

# Initialize the SQLite database on startup
init_db()

# ─── Server-side Liveness Session Store ──────────────────────────────────────
# Maps session_token -> {'verified': bool, 'encoding': np.ndarray or None}
# Prevents API bypass by requiring server-verified liveness tokens.
import threading
_liveness_store = {}
_liveness_lock = threading.Lock()

def _mark_liveness_verified(session_token, face_encoding=None):
    with _liveness_lock:
        _liveness_store[session_token] = {
            'verified': True,
            'encoding': face_encoding,
        }

def _is_liveness_verified(session_token):
    with _liveness_lock:
        entry = _liveness_store.get(session_token)
        return entry is not None and entry.get('verified', False)

def _consume_liveness(session_token):
    """Check and consume (invalidate) a liveness token (one-time use)."""
    with _liveness_lock:
        entry = _liveness_store.pop(session_token, None)
        return entry is not None and entry.get('verified', False)


# ─── Helpers & Decorators ────────────────────────────────────────────────────
def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def unique_filename(filename):
    """Prepend a timestamp to filename to make it unique."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    return f"{timestamp}_{secure_filename(filename)}"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth_page'))
        # Guard: session user must still exist in DB (handles DB resets)
        if not get_user_by_id(session['user']['id']):
            session.clear()
            flash('Your session has expired. Please log in again.', 'warning')
            return redirect(url_for('auth_page'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('auth_page'))
            # Guard: session user must still exist in DB (handles DB resets)
            if not get_user_by_id(session['user']['id']):
                session.clear()
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('auth_page'))
            if session['user']['role'] not in roles:
                flash("You do not have permission to access that page.", "warning")
                role = session['user']['role']
                if role == 'super_admin':
                    return redirect(url_for('super_admin_dashboard'))
                elif role == 'photographer':
                    return redirect(url_for('photographer_dashboard'))
                elif role == 'assistant':
                    return redirect(url_for('assistant_dashboard'))
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ─── Page Routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Landing page displaying active and published events."""
    events = get_all_published_active_events()
    return render_template('frontend/index.html', events=events)


@app.route('/auth')
def auth_page():
    """Authentication page for Login/Signup."""
    if 'user' in session:
        role = session['user']['role']
        if role == 'super_admin':
            return redirect(url_for('super_admin_dashboard'))
        elif role == 'photographer':
            return redirect(url_for('photographer_dashboard'))
        elif role == 'assistant':
            return redirect(url_for('assistant_dashboard'))
    return render_template('frontend/auth.html')


@app.route('/event/<int:event_id>')
def event_detail(event_id):
    """Event detail page. Shows webcam face scan controls only."""
    event = get_event_by_id(event_id)
    if not event or not event['is_active']:
        flash("This event is inactive, expired, or does not exist.", "warning")
        return redirect(url_for('index'))
    return render_template('frontend/event_detail.html', event=event)


# ─── Auth API ────────────────────────────────────────────────────────────────

@app.route('/api/register', methods=['POST'])
def api_register():
    """Register a new photographer."""
    data = request.form
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    res = create_user(username, password, 'photographer')
    return jsonify(res)


@app.route('/api/login', methods=['POST'])
def api_login():
    """Authenticate and log in any user role."""
    data = request.form
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    user = verify_user(username, password)
    if user:
        session['user'] = user
        # Determine landing page
        if user['role'] == 'super_admin':
            redirect_url = url_for('super_admin_dashboard')
        elif user['role'] == 'photographer':
            redirect_url = url_for('photographer_dashboard')
        else:
            redirect_url = url_for('assistant_dashboard')
        return jsonify({'success': True, 'redirect': redirect_url})

    return jsonify({'success': False, 'message': 'Invalid username or password.'}), 401


@app.route('/logout')
def logout():
    """Clear session and redirect to landing page."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))


# ─── User Profile API ────────────────────────────────────────────────────────

@app.route('/api/user/profile', methods=['POST'])
def api_update_user_profile():
    """Update profile settings (name, email, username, password) for logged in user."""
    if not session.get('user'):
        return jsonify({'success': False, 'message': 'Unauthorized. Please sign in.'}), 401
    
    user_id = session['user']['id']
    data = request.form
    name = data.get('name')
    email = data.get('email')
    username = data.get('username')
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    res = update_user_profile(
        user_id=user_id,
        name=name,
        email=email,
        username=username,
        current_password=current_password,
        new_password=new_password
    )

    if res.get('success') and 'user' in res:
        session['user']['username'] = res['user']['username']
        session['user']['name'] = res['user']['name']
        session['user']['email'] = res['user']['email']
        session.modified = True

    return jsonify(res)


# ─── Profile Picture API ──────────────────────────────────────────────────────

def _remove_old_profile_pic(profile_pic_path):
    """Best-effort removal of a previously stored profile picture file."""
    if profile_pic_path and profile_pic_path.startswith('static/uploads/profile_pics/') and os.path.exists(profile_pic_path):
        try:
            os.remove(profile_pic_path)
        except OSError:
            pass


@app.route('/api/user/profile-pic', methods=['POST', 'DELETE'])
@login_required
def api_profile_pic():
    """Upload, replace or remove the logged-in user's profile picture."""
    if not session.get('user'):
        return jsonify({'success': False, 'message': 'Unauthorized. Please sign in.'}), 401

    user_id = session['user']['id']
    u_info = get_user_by_id(user_id) or {}
    old_path = u_info.get('profile_pic') or ''

    if request.method == 'DELETE':
        _remove_old_profile_pic(old_path)
        update_user_profile_pic(user_id, '')
        session['user']['profile_pic'] = ''
        session.modified = True
        return jsonify({'success': True, 'message': 'Profile picture removed.'})

    # POST: upload / replace
    if 'profile_pic' not in request.files:
        return jsonify({'success': False, 'message': 'No image provided.'}), 400

    file = request.files['profile_pic']
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No image selected.'}), 400
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Unsupported format. Use JPG, PNG or WEBP.'}), 400

    os.makedirs(PROFILE_PIC_FOLDER, exist_ok=True)

    fname = f"user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{secure_filename(file.filename)}"
    save_path = os.path.join(PROFILE_PIC_FOLDER, fname)
    file.save(save_path)

    relative_path = save_path.replace('\\', '/')

    res = update_user_profile_pic(user_id, relative_path)
    if res['success']:
        _remove_old_profile_pic(old_path)
        session['user']['profile_pic'] = relative_path
        session.modified = True
        return jsonify({'success': True, 'message': 'Profile picture updated.', 'profile_pic': relative_path})
    return jsonify(res), 400


# ─── Dashboards ──────────────────────────────────────────────────────────────

@app.route('/dashboard')
@role_required('photographer')
def photographer_dashboard():
    """Photographer Dashboard."""
    p_id = session['user']['id']
    u_info = get_user_by_id(p_id)
    if u_info:
        session['user']['name'] = u_info.get('name', '')
        session['user']['email'] = u_info.get('email', '')
        session['user']['username'] = u_info.get('username', '')
        session['user']['profile_pic'] = u_info.get('profile_pic', '')
        session.modified = True

    events = get_events_by_photographer(p_id)
    assistants = get_assistants_by_photographer(p_id)
    stats = get_photographer_stats(p_id)
    return render_template('photographer/dashboard.html', events=events, assistants=assistants, stats=stats)


@app.route('/api/overview/downloads')
@role_required('photographer')
def api_photographer_daily_downloads():
    """Return daily photo-download totals for the logged-in photographer."""
    try:
        days = request.args.get('days', 30, type=int)
        days = max(7, min(days, 90))  # clamp to 7–90
        p_id = session['user']['id']
        data = get_photographer_daily_downloads(p_id, days)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/overview/event-stats')
@role_required('photographer')
def api_photographer_event_stats():
    """Return per-event photo/download stats for the overview pie & bar charts."""
    try:
        p_id = session['user']['id']
        data = get_photographer_event_chart_data(p_id)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/assistant/dashboard')
@role_required('assistant')
def assistant_dashboard():
    """Assistant Dashboard."""
    a_id = session['user']['id']
    u_info = get_user_by_id(a_id)
    if u_info:
        session['user']['name'] = u_info.get('name', '')
        session['user']['email'] = u_info.get('email', '')
        session['user']['username'] = u_info.get('username', '')
        session['user']['profile_pic'] = u_info.get('profile_pic', '')
        session.modified = True

    assigned_events = get_assigned_events_for_assistant(a_id)
    return render_template('assistant/assistant_dashboard.html', events=assigned_events)


@app.route('/admin/dashboard')
@role_required('super_admin')
def super_admin_dashboard():
    """Super Admin Dashboard."""
    admin_id = session['user']['id']
    u_info = get_user_by_id(admin_id)
    if u_info:
        session['user']['name'] = u_info.get('name', '')
        session['user']['email'] = u_info.get('email', '')
        session['user']['username'] = u_info.get('username', '')
        session['user']['profile_pic'] = u_info.get('profile_pic', '')
        session.modified = True

    stats = get_global_stats()
    users = get_all_users_with_creators()
    events = get_all_events_with_creators()
    return render_template('super_admin/super_admin.html', stats=stats, users=users, events=events)


# ─── Super Admin User Management API ─────────────────────────────────────────

@app.route('/api/admin/user/create', methods=['POST'])
@role_required('super_admin')
def api_admin_create_user():
    """Create a new photographer or assistant account from the super admin portal."""
    data = request.form
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')

    if not username or not password or role not in ('photographer', 'assistant'):
        return jsonify({'success': False, 'message': 'Username, password and a valid role are required.'}), 400

    res = create_user(username, password, role, created_by=session['user']['id'])
    if res['success']:
        return jsonify({'success': True, 'message': f'{role.title()} account created successfully.'})
    return jsonify(res), 400


@app.route('/api/admin/user/update', methods=['POST'])
@role_required('super_admin')
def api_admin_update_user():
    """Update user details from the super admin portal."""
    data = request.form
    try:
        user_id = int(data.get('user_id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid user.'}), 400

    target = get_user_by_id(user_id)
    if not target:
        return jsonify({'success': False, 'message': 'User account not found.'}), 404

    # Never allow changing your own role or demoting the last super admin
    role = data.get('role')
    if user_id == session['user']['id']:
        role = None
    elif target['role'] == 'super_admin' and role and role != 'super_admin':
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'super_admin'").fetchone()[0]
        conn.close()
        if count <= 1:
            return jsonify({'success': False, 'message': 'Cannot demote the last super admin account.'}), 400

    res = update_user(
        user_id,
        name=data.get('name'),
        email=data.get('email'),
        username=data.get('username'),
        role=role,
        new_password=data.get('new_password')
    )
    if res['success']:
        return jsonify(res)
    return jsonify(res), 400


@app.route('/api/admin/user/delete', methods=['POST'])
@role_required('super_admin')
def api_admin_delete_user():
    """Delete a user account."""
    data = request.form
    try:
        user_id = int(data.get('user_id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid user.'}), 400

    if user_id == session['user']['id']:
        return jsonify({'success': False, 'message': 'You cannot delete your own account.'}), 400

    target = get_user_by_id(user_id)
    if not target:
        return jsonify({'success': False, 'message': 'User account not found.'}), 404

    if target['role'] == 'super_admin':
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'super_admin'").fetchone()[0]
        conn.close()
        if count <= 1:
            return jsonify({'success': False, 'message': 'Cannot delete the last super admin account.'}), 400

    res = delete_user(user_id)
    if res['success']:
        return jsonify(res)
    return jsonify(res), 400


# ─── Event Management API ────────────────────────────────────────────────────

@app.route('/api/event/create', methods=['POST'])
@role_required('photographer')
def api_create_event():
    """Create a new event."""
    name = request.form.get('name')
    description = request.form.get('description', '')
    deactivation_date = request.form.get('deactivation_date', None) or None
    download_limit = request.form.get('download_limit', 1)

    if not name:
        return jsonify({'success': False, 'message': 'Event name is required.'}), 400

    created_by = session['user']['id']

    # Double-check user still exists (belt-and-suspenders against FK failure)
    if not get_user_by_id(created_by):
        session.clear()
        return jsonify({'success': False, 'message': 'Session invalid — please log in again.'}), 401

    try:
        event_id = create_event(
            name=name,
            description=description,
            created_by=created_by,
            status='unpublished',
            deactivation_date=deactivation_date,
            download_limit=download_limit
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to create event: {str(e)}'}), 500

    flash(f"Event '{name}' created successfully as unpublished.", "success")
    return jsonify({'success': True, 'event_id': event_id})


@app.route('/api/event/<int:event_id>/update', methods=['POST'])
@login_required
def api_update_event(event_id):
    """Update event configuration."""
    event = get_event_by_id(event_id)
    if not event:
        return jsonify({'success': False, 'message': 'Event not found.'}), 404

    # Authorization Check
    user_id = session['user']['id']
    role = session['user']['role']

    if role == 'photographer':
        if event['created_by'] != user_id:
            return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    elif role == 'assistant':
        perms = get_assistant_permissions_for_event(user_id, event_id)
        if not perms:
            return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    elif role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403

    # Extract update fields
    data = request.form
    name = data.get('name')
    description = data.get('description')
    status = data.get('status')
    deactivation_date = data.get('deactivation_date')
    download_limit = data.get('download_limit')

    # Assistants can ONLY deactivate (update status or toggle status) if they have can_deactivate permission
    if role == 'assistant':
        # Assistant cannot update limit, name, description, etc.
        perms = get_assistant_permissions_for_event(user_id, event_id)
        if not perms['can_deactivate']:
            return jsonify({'success': False, 'message': 'You do not have permission to modify this event.'}), 403
        
        # Only status can be modified by assistant
        update_event(event_id, status=status)
        return jsonify({'success': True, 'message': 'Event status updated successfully.'})

    # Photographers and Admin can update everything
    update_event(
        event_id,
        name=name,
        description=description,
        status=status,
        deactivation_date=deactivation_date,
        download_limit=download_limit
    )
    return jsonify({'success': True, 'message': 'Event updated successfully.'})


# ─── Assistant Management API ────────────────────────────────────────────────

@app.route('/api/assistant/create', methods=['POST'])
@role_required('photographer')
def api_create_assistant():
    """Create an assistant sub-user."""
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    creator_id = session['user']['id']
    res = create_user(username, password, 'assistant', created_by=creator_id)
    return jsonify(res)


@app.route('/api/event/assign-assistant', methods=['POST'])
@role_required('photographer')
def api_assign_assistant():
    """Assign an assistant to an event with specific permissions."""
    event_id = request.form.get('event_id')
    user_id = request.form.get('user_id')
    can_upload = 1 if request.form.get('can_upload') else 0
    can_delete = 1 if request.form.get('can_delete') else 0
    can_deactivate = 1 if request.form.get('can_deactivate') else 0

    if not event_id or not user_id:
        return jsonify({'success': False, 'message': 'Missing event ID or user ID.'}), 400

    # Ensure photographer owns the event
    event = get_event_by_id(event_id)
    if not event or event['created_by'] != session['user']['id']:
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403

    assign_assistant_to_event(event_id, user_id, can_upload, can_delete, can_deactivate)
    return jsonify({'success': True, 'message': 'Assistant permissions assigned.'})


@app.route('/api/event/remove-assistant', methods=['POST'])
@role_required('photographer')
def api_remove_assistant():
    """Remove assistant from an event."""
    event_id = request.form.get('event_id')
    user_id = request.form.get('user_id')

    if not event_id or not user_id:
        return jsonify({'success': False, 'message': 'Missing event ID or user ID.'}), 400

    # Ensure photographer owns the event
    event = get_event_by_id(event_id)
    if not event or event['created_by'] != session['user']['id']:
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403

    remove_assistant_from_event(event_id, user_id)
    return jsonify({'success': True, 'message': 'Assistant unassigned.'})


@app.route('/api/event/<int:event_id>/assignments')
@login_required
def api_event_assignments(event_id):
    """Retrieve all assignments for an event."""
    event = get_event_by_id(event_id)
    if not event:
        return jsonify({'success': False, 'message': 'Event not found.'}), 404

    user_id = session['user']['id']
    role = session['user']['role']
    if role == 'photographer' and event['created_by'] != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    elif role != 'photographer' and role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403

    assignments = get_assignments_by_event(event_id)
    return jsonify({'success': True, 'assignments': assignments})


# ─── Photo Upload & Management API ───────────────────────────────────────────

@app.route('/api/event/<int:event_id>/photos')
@login_required
def api_event_photos(event_id):
    """Retrieve all images uploaded to an event (JSON format)."""
    event = get_event_by_id(event_id)
    if not event:
        return jsonify({'success': False, 'message': 'Event not found.'}), 404

    # Auth check
    user_id = session['user']['id']
    role = session['user']['role']

    if role == 'photographer' and event['created_by'] != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    elif role == 'assistant':
        perms = get_assistant_permissions_for_event(user_id, event_id)
        if not perms:
            return jsonify({'success': False, 'message': 'Unauthorized.'}), 403

    images = get_images_by_event(event_id)
    return jsonify({'success': True, 'images': images})


@app.route('/api/event/<int:event_id>/upload', methods=['POST'])
@login_required
def api_upload_photos(event_id):
    """Upload bulk images to an event. Detects faces, registers them in DB."""
    event = get_event_by_id(event_id)
    if not event:
        return jsonify({'success': False, 'message': 'Event not found.'}), 404

    user_id = session['user']['id']
    role = session['user']['role']

    # Validate upload permissions
    if role == 'photographer':
        if event['created_by'] != user_id:
            return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    elif role == 'assistant':
        perms = get_assistant_permissions_for_event(user_id, event_id)
        if not perms or not perms['can_upload']:
            return jsonify({'success': False, 'message': 'You do not have permission to upload photos.'}), 403
    elif role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403

    if 'images' not in request.files:
        return jsonify({'success': False, 'message': 'No images provided.'}), 400

    files = request.files.getlist('images')
    results = []

    # Organize uploads under static/uploads/<event_id>/
    event_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(event_id))
    os.makedirs(event_upload_dir, exist_ok=True)

    for file in files:
        if file.filename == '':
            continue
        if not allowed_file(file.filename):
            results.append({'file': file.filename, 'status': 'skipped - unsupported format'})
            continue

        # Save file to disk
        fname = unique_filename(file.filename)
        save_path = os.path.join(event_upload_dir, fname)
        file.save(save_path)

        # Normalize path for web storage
        relative_path = save_path.replace('\\', '/')

        # Save basic image record in DB
        image_id = save_image_record(event_id, relative_path, user_id)

        # Extract face encodings
        encodings, face_count = extract_face_encodings(save_path)
        
        # Save face encodings linked to image_id
        for enc in encodings:
            save_face_encoding(image_id, enc)

        results.append({
            'file': file.filename,
            'status': 'success',
            'faces': face_count,
            'image_id': image_id,
            'path': '/' + relative_path
        })

    return jsonify({'success': True, 'results': results})


@app.route('/api/event/<int:event_id>/image/<int:image_id>', methods=['DELETE'])
@login_required
def api_delete_photo(event_id, image_id):
    """Delete an image from an event."""
    event = get_event_by_id(event_id)
    if not event:
        return jsonify({'success': False, 'message': 'Event not found.'}), 404

    user_id = session['user']['id']
    role = session['user']['role']

    # Validate delete permissions
    if role == 'photographer':
        if event['created_by'] != user_id:
            return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    elif role == 'assistant':
        perms = get_assistant_permissions_for_event(user_id, event_id)
        if not perms or not perms['can_delete']:
            return jsonify({'success': False, 'message': 'You do not have permission to delete photos.'}), 403
    elif role != 'super_admin':
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403

    # Check if image belongs to event
    image = get_image_by_id(image_id)
    if not image or image['event_id'] != event_id:
        return jsonify({'success': False, 'message': 'Image not found.'}), 404

    # Delete physical file from disk
    file_path = image['image_path']
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"[Error] Failed to delete file {file_path}: {e}")

    # Delete record (cascades face_encodings and downloads)
    delete_image_record(image_id)
    return jsonify({'success': True, 'message': 'Image deleted successfully.'})


# ─── Public Matching & Download API ──────────────────────────────────────────

@app.route('/api/event/<int:event_id>/liveness', methods=['POST'])
def api_liveness_check(event_id):
    """
    Liveness / anti-spoofing check (v2).
    Accepts two frames (neutral + action) and verifies:
      1. The requested facial action was performed (mouth-open or blink)
      2. Both frames contain the SAME person (face encoding cross-check)
      3. The captured images show a real face (texture/spoof analysis)
      4. Stores verification server-side (session_token required)

    On success, marks the session_token as liveness-verified so the
    match API can check it server-side rather than trusting a client flag.
    """
    import face_recognition as fr
    import numpy as np

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Missing request body.'}), 400

        session_token = data.get('session_token', '')
        if not session_token:
            return jsonify({'success': False, 'message': 'Missing session_token.'}), 400

        challenge    = data.get('challenge')           # 'mouth' | 'blink'
        frame_neutral_b64 = data.get('frame_neutral')
        frame_action_b64  = data.get('frame_action')
        if not challenge or not frame_neutral_b64 or not frame_action_b64:
            return jsonify({'success': False, 'message': 'Missing liveness frames or challenge type.'}), 400

        uid = datetime.now().strftime('%H%M%S_%f')
        tmp_neutral = os.path.join(app.config['UPLOAD_FOLDER'], f'_lv_neutral_{uid}.jpg')
        tmp_action  = os.path.join(app.config['UPLOAD_FOLDER'], f'_lv_action_{uid}.jpg')

        try:
            decode_base64_image(frame_neutral_b64, tmp_neutral)
            decode_base64_image(frame_action_b64,  tmp_action)
        except Exception as e:
            return jsonify({'success': False, 'message': f'Frame decode error: {str(e)}'}), 400

        def _cleanup():
            for p in [tmp_neutral, tmp_action]:
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass

        # ── Load images ──────────────────────────────────────────────────────
        try:
            img_n = fr.load_image_file(tmp_neutral)
            img_a = fr.load_image_file(tmp_action)
        except Exception as e:
            _cleanup()
            return jsonify({'success': False, 'message': f'Image load error: {str(e)}'}), 400

        # ── Step 1: Detect face locations once on scaled images, then scale up ──
        import cv2

        try:
            # Detect locations on scaled neutral image
            img_n_bgr = cv2.imread(tmp_neutral)
            if img_n_bgr is not None:
                img_n_small = cv2.resize(img_n_bgr, (0, 0), fx=0.5, fy=0.5)
                img_n_small_rgb = cv2.cvtColor(img_n_small, cv2.COLOR_BGR2RGB)
                locs_n_small = fr.face_locations(img_n_small_rgb, model='hog')
                locs_n = [(top * 2, right * 2, bottom * 2, left * 2) for (top, right, bottom, left) in locs_n_small]
            else:
                locs_n = fr.face_locations(img_n, model='hog')

            # Detect locations on scaled action image
            img_a_bgr = cv2.imread(tmp_action)
            if img_a_bgr is not None:
                img_a_small = cv2.resize(img_a_bgr, (0, 0), fx=0.5, fy=0.5)
                img_a_small_rgb = cv2.cvtColor(img_a_small, cv2.COLOR_BGR2RGB)
                locs_a_small = fr.face_locations(img_a_small_rgb, model='hog')
                locs_a = [(top * 2, right * 2, bottom * 2, left * 2) for (top, right, bottom, left) in locs_a_small]
            else:
                locs_a = fr.face_locations(img_a, model='hog')
        except Exception as e:
            print(f"[Liveness] Optimization error: {e}")
            _cleanup()
            return jsonify({'success': False, 'message': 'Failed to process camera frames.'}), 200

        if not locs_n or not locs_a:
            _cleanup()
            return jsonify({
                'success': False,
                'message': 'Could not detect a face in one or both frames. Make sure your face is clearly visible.'
            }), 200

        # Compute landmarks using the pre-computed locations
        lm_neutral = fr.face_landmarks(img_n, face_locations=locs_n)
        lm_action  = fr.face_landmarks(img_a, face_locations=locs_a)

        if not lm_neutral or not lm_action:
            _cleanup()
            return jsonify({
                'success': False,
                'message': 'Could not extract landmarks. Position your face clearly.'
            }), 200

        lm_n = lm_neutral[0]
        lm_a = lm_action[0]

        # ── Step 2: Extract face encodings using the same locations ──────
        enc_n_list = fr.face_encodings(img_n, known_face_locations=locs_n)
        enc_a_list = fr.face_encodings(img_a, known_face_locations=locs_a)

        enc_n = enc_n_list[0] if enc_n_list else None
        enc_a = enc_a_list[0] if enc_a_list else None

        # ── Step 3: Spoof / texture analysis on both frames ──────────────────
        spoof_n = analyze_spoof(tmp_neutral)
        spoof_a = analyze_spoof(tmp_action)

        # Combined spoof risk – if either frame looks suspicious, flag it
        spoof_risk = max(spoof_n['risk'], spoof_a['risk'])
        spoof_flags = list(set(spoof_n['flags'] + spoof_a['flags']))

        # ── Step 4: Verify the requested action ──────────────────────────────
        action_passed = False
        if challenge == 'mouth':
            ratio_neutral = get_mouth_open_ratio(lm_n)
            ratio_action  = get_mouth_open_ratio(lm_a)
            action_passed = (ratio_action >= 0.12) and (ratio_action >= ratio_neutral * 1.8)
            print(f'[Liveness] mouth: neutral={ratio_neutral:.4f}, action={ratio_action:.4f}, passed={action_passed}')

        elif challenge == 'blink':
            def _ear(eye_pts):
                pts = np.array(eye_pts)
                v1 = np.linalg.norm(pts[1] - pts[5])
                v2 = np.linalg.norm(pts[2] - pts[4])
                h  = np.linalg.norm(pts[0] - pts[3])
                return (v1 + v2) / (2.0 * h + 1e-6)

            def _avg_ear(lm):
                le = _ear(lm.get('left_eye',  []))
                re = _ear(lm.get('right_eye', []))
                return (le + re) / 2.0

            ear_n = _avg_ear(lm_n)
            ear_a = _avg_ear(lm_a)
            action_passed = (ear_a <= 0.20) or (ear_n - ear_a >= 0.08)
            print(f'[Liveness] blink: neutral_ear={ear_n:.4f}, action_ear={ear_a:.4f}, passed={action_passed}')

        else:
            _cleanup()
            return jsonify({'success': False, 'message': 'Unknown challenge type.'}), 400

        # ── Step 5: Same-face cross-check ────────────────────────────────────
        same_face, face_dist = verify_same_face(enc_n, enc_a, threshold=0.5) if (enc_n is not None and enc_a is not None) else (False, 1.0)
        if not same_face:
            _cleanup()
            return jsonify({
                'success': False,
                'message': 'Face mismatch detected between frames. Please use the same person\'s face throughout.'
            }), 200

        # ── Step 6: Evaluate overall result ──────────────────────────────────
        reject_reasons = []
        if not action_passed:
            reject_reasons.append('action_not_performed')
        if spoof_risk >= 0.5:
            reject_reasons.append('spoof_suspected')
            print(f'[Liveness] Spoof risk={spoof_risk:.2f}, flags={spoof_flags}')

        _cleanup()

        if not reject_reasons:
            # Mark this session as liveness-verified on the server
            _mark_liveness_verified(session_token, face_encoding=enc_n)

            # Check if this is the final challenge in a multi-challenge sequence
            return jsonify({
                'success': True,
                'message': 'Liveness verified.',
                'challenge_completed': challenge,
                'more_challenges_remaining': False
            })
        else:
            reason_text = 'Action not performed. ' if 'action_not_performed' in reject_reasons else ''
            if 'spoof_suspected' in reject_reasons:
                reason_text += 'Photo or screen detected. Please use your real face.'
            return jsonify({
                'success': False,
                'message': reason_text or 'Liveness check failed. Please try again.'
            }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Liveness error: {str(e)}'}), 500


@app.route('/api/event/<int:event_id>/match', methods=['POST'])
def api_match_face(event_id):
    """Perform face matching in an event. Requires server-side liveness verification. Filters out files matching user's download limit."""
    try:
        data = request.get_json()
        if not data or 'image' not in data or 'session_token' not in data:
            return jsonify({'success': False, 'message': 'Missing image or session token.'}), 400

        # ── Liveness gate (server-side) ────────────────────────────────────────
        session_token = data.get('session_token', '')
        if not session_token or not _consume_liveness(session_token):
            return jsonify({'success': False, 'message': 'Liveness check not completed. Please pass the anti-spoof challenge first.'}), 403
        image_data = data['image']
        threshold = float(data.get('threshold', 0.5))

        # Event status check
        event = get_event_by_id(event_id)
        if not event or not event['is_active']:
            return jsonify({'success': False, 'message': 'Event is not active or does not exist.'}), 404

        # Decode and save temporary query face
        tmp_filename = f"_tmp_scan_{event_id}_{datetime.now().strftime('%H%M%S_%f')}.jpg"
        tmp_path = os.path.join(app.config['UPLOAD_FOLDER'], tmp_filename)

        try:
            decode_base64_image(image_data, tmp_path)
        except Exception as e:
            return jsonify({'success': False, 'message': f'Image decode error: {str(e)}'}), 400

        # Extract user face encoding
        user_encodings, face_count = extract_face_encodings(tmp_path)

        # Clean up temporary query face
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        if face_count == 0:
            return jsonify({'success': False, 'message': 'No face detected in scan. Center your face and try again.'}), 200

        # Load all stored encodings for this specific event
        stored = get_face_encodings_by_event(event_id)
        if not stored:
            return jsonify({'success': False, 'message': 'No photos have been uploaded to this event yet.'}), 200

        # Perform matching
        matched_fe_ids = match_face_encoding(user_encodings[0], stored, threshold)
        if not matched_fe_ids:
            return jsonify({'success': False, 'message': 'No matching photos found for your face.'}), 200

        # Build unique mappings
        matched_images_map = {}
        for rec in stored:
            if rec[0] in matched_fe_ids:
                matched_images_map[rec[1]] = rec[3]

        matched_image_paths = list(matched_images_map.keys())

        # Apply download limits filter
        allowed_image_paths = filter_downloaded_images(event_id, matched_image_paths, session_token)

        results = []
        for path in allowed_image_paths:
            img_id = matched_images_map[path]
            results.append({
                'id': img_id,
                'path': '/' + path
            })

        return jsonify({
            'success': True,
            'count': len(results),
            'images': results
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Internal match error: {str(e)}'}), 500


# ─── User Profile API ─────────────────────────────────────────────────────────

@app.route('/api/user/profile', methods=['POST'])
@login_required
def api_update_profile():
    """Update the currently logged-in user's profile (name, email, username, password)."""
    user_id = session['user']['id']
    data = request.get_json() or {}

    name             = data.get('name', '').strip()
    email            = data.get('email', '').strip()
    username         = data.get('username', '').strip()
    current_password = data.get('current_password', '').strip()
    new_password     = data.get('new_password', '').strip()

    if not username:
        return jsonify({'success': False, 'message': 'Username is required.'}), 400

    result = update_user_profile(
        user_id,
        name=name if name else None,
        email=email if email else None,
        username=username,
        current_password=current_password if current_password else None,
        new_password=new_password if new_password else None,
    )

    if result['success'] and 'user' in result:
        # Refresh session so header and avatar update immediately
        session['user'] = {
            'id':       result['user']['id'],
            'username': result['user']['username'],
            'name':     result['user'].get('name', ''),
            'email':    result['user'].get('email', ''),
            'role':     result['user']['role'],
        }
        session.modified = True

    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code



@app.route('/api/download/<int:image_id>')
def api_download_image(image_id):
    """Download image endpoint. Checks and records download counts per session."""
    session_token = request.args.get('token')
    if not session_token:
        return "Missing session token", 400

    image = get_image_by_id(image_id)
    if not image:
        return "Image not found", 404

    event = get_event_by_id(image['event_id'])
    if not event:
        return "Event not found", 404

    # Download limit check
    conn = get_connection()
    row = conn.execute(
        'SELECT COALESCE(download_count, 0) as download_count FROM downloads WHERE image_id = ? AND session_token = ?',
        (image_id, session_token)
    ).fetchone()
    conn.close()

    current_downloads = row['download_count'] if row else 0
    if current_downloads >= event['download_limit']:
        return "Download limit reached for this image.", 403

    # Record download
    track_download(image_id, session_token)

    # Deliver file
    directory, filename = os.path.split(image['image_path'])
    return send_from_directory(directory, filename, as_attachment=True)


# ─── Static file helper (Fallback) ───────────────────────────────────────────
@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded images."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
