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
    get_mouth_open_ratio
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
    get_all_users_with_creators
)

# ─── App Configuration ───────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'super-secret-key-for-photographer-app-12345'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB max upload size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize the SQLite database on startup
init_db()


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
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('auth_page'))
            if session['user']['role'] not in roles:
                flash("You do not have permission to access that page.", "warning")
                # Redirect to their appropriate dashboard
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


# ─── Dashboards ──────────────────────────────────────────────────────────────

@app.route('/dashboard')
@role_required('photographer')
def photographer_dashboard():
    """Photographer Dashboard."""
    p_id = session['user']['id']
    events = get_events_by_photographer(p_id)
    assistants = get_assistants_by_photographer(p_id)
    stats = get_photographer_stats(p_id)
    return render_template('photographer/dashboard.html', events=events, assistants=assistants, stats=stats)


@app.route('/assistant/dashboard')
@role_required('assistant')
def assistant_dashboard():
    """Assistant Dashboard."""
    a_id = session['user']['id']
    assigned_events = get_assigned_events_for_assistant(a_id)
    return render_template('assistant/assistant_dashboard.html', events=assigned_events)


@app.route('/admin/dashboard')
@role_required('super_admin')
def super_admin_dashboard():
    """Super Admin Dashboard."""
    stats = get_global_stats()
    users = get_all_users_with_creators()
    events = get_all_events_with_creators()
    return render_template('super_admin/super_admin.html', stats=stats, users=users, events=events)


# ─── Event Management API ────────────────────────────────────────────────────

@app.route('/api/event/create', methods=['POST'])
@role_required('photographer')
def api_create_event():
    """Create a new event."""
    name = request.form.get('name')
    description = request.form.get('description', '')
    deactivation_date = request.form.get('deactivation_date', None)
    download_limit = request.form.get('download_limit', 1)

    if not name:
        return jsonify({'success': False, 'message': 'Event name is required.'}), 400

    created_by = session['user']['id']
    event_id = create_event(
        name=name,
        description=description,
        created_by=created_by,
        status='unpublished',
        deactivation_date=deactivation_date,
        download_limit=download_limit
    )
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

@app.route('/api/event/<int:event_id>/match', methods=['POST'])
def api_match_face(event_id):
    """Perform face matching in an event. Filters out files matching user's download limit."""
    try:
        data = request.get_json()
        if not data or 'image' not in data or 'session_token' not in data:
            return jsonify({'success': False, 'message': 'Missing image or session token.'}), 400

        session_token = data['session_token']
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
    app.run(debug=True, host='0.0.0.0', port=5000)
