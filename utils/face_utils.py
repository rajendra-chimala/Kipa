"""
utils/face_utils.py – Face processing utilities
All face_recognition calls are centralised here to keep app.py clean.
"""

import base64
import os
import numpy as np
import face_recognition


def extract_face_encodings(image_path: str):
    """
    Load an image, detect all faces, and return their 128-d encodings.
    Uses multi-stage detection and jitter resampling (num_jitters=2) for high accuracy,
    especially across eyewear variations (glasses on/off).

    Args:
        image_path: Absolute or relative path to the image file.

    Returns:
        Tuple (encodings, face_count):
            encodings  – list of numpy arrays (one per detected face)
            face_count – integer count of detected faces
    """
    try:
        # Load image into RGB array (face_recognition uses RGB, not BGR)
        image = face_recognition.load_image_file(image_path)

        # Detect face locations using HOG model; retry with upsample=2 if 0 faces found
        face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=1, model='hog')
        if not face_locations:
            face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=2, model='hog')

        # Compute 128-d encodings for every detected face with num_jitters=2 for eyewear resilience
        encodings = face_recognition.face_encodings(image, known_face_locations=face_locations, num_jitters=2)

        return encodings, len(encodings)

    except Exception as e:
        print(f'[FaceUtils] Error processing {image_path}: {e}')
        return [], 0


def match_face_encoding(user_encoding: np.ndarray, stored_records: list, threshold: float = 0.58):
    """
    Compare a user's face encoding against a list of stored encodings.

    Args:
        user_encoding:   128-d numpy array of the user's face.
        stored_records:  List of (id, image_path, numpy_encoding) tuples from DB.
        threshold:       Maximum face distance to consider a match (lower = stricter).
                         Default 0.58 accommodates face variations with/without glasses while maintaining high precision (dlib standard = 0.60).

    Returns:
        List of record IDs that matched.
    """
    matched_ids = []

    if user_encoding is None or len(stored_records) == 0:
        return matched_ids

    # Extract just the encodings for bulk comparison
    known_encodings = [rec[2] for rec in stored_records]
    record_ids      = [rec[0] for rec in stored_records]

    # face_distance returns an array of distances (0 = identical, 1 = very different)
    distances = face_recognition.face_distance(known_encodings, user_encoding)

    for idx, distance in enumerate(distances):
        if distance <= threshold:
            matched_ids.append(record_ids[idx])
            print(f'[FaceUtils] Match found – record {record_ids[idx]}, distance={distance:.4f}')

    return matched_ids


def decode_base64_image(base64_string: str, output_path: str):
    """
    Decode a base64-encoded image (from webcam canvas) and save it to disk.

    Args:
        base64_string:  Raw base64 string, optionally with data URI prefix.
        output_path:    File path where the decoded image should be saved.
    """
    # Strip the data URI prefix if present (e.g. "data:image/jpeg;base64,...")
    if ',' in base64_string:
        base64_string = base64_string.split(',', 1)[1]

    image_bytes = base64.b64decode(base64_string)

    with open(output_path, 'wb') as f:
        f.write(image_bytes)


def draw_face_boxes(image_path: str, face_locations: list):
    """
    Optional helper – not used in routes but available for debugging.
    Returns a list of dicts describing each detected face bounding box.
    """
    boxes = []
    for (top, right, bottom, left) in face_locations:
        boxes.append({'top': top, 'right': right, 'bottom': bottom, 'left': left})
    return boxes


def get_face_encoding_from_image(image_path: str):
    """
    Extract a single face encoding from an image.
    Returns (encoding, None) on success, or (None, error_msg) on failure.
    """
    try:
        image = face_recognition.load_image_file(image_path)
        locations = face_recognition.face_locations(image, number_of_times_to_upsample=1, model='hog')
        if not locations:
            locations = face_recognition.face_locations(image, number_of_times_to_upsample=2, model='hog')
        if not locations:
            return None, 'No face detected'
        encodings = face_recognition.face_encodings(image, known_face_locations=locations, num_jitters=2)
        if not encodings:
            return None, 'Could not compute face encoding'
        return encodings[0], None
    except Exception as e:
        return None, str(e)


def verify_same_face(enc1, enc2, threshold=0.58):
    """
    Verify that two face encodings belong to the same person.
    Returns (True, distance) if match, (False, distance) otherwise.
    """
    if enc1 is None or enc2 is None:
        return False, 1.0
    distance = face_recognition.face_distance([enc1], enc2)[0]
    return bool(distance <= threshold), float(distance)


def analyze_spoof(image_path: str):
    """
    Basic spoof / photo-detection analysis.
    Checks for:
      - Laplacian variance (blur indicator – printed photos often have uniform blur)
      - Edge ratio (screen/paper edges create sharp boundaries)
    Returns a dict with risk indicators.
    """
    import cv2

    img = cv2.imread(image_path)
    if img is None:
        return {'risk': 0.5, 'flags': ['could_not_read']}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 1. Laplacian variance – measures focal sharpness
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    # Very low variance = overly smooth (possible printed photo blur)
    # Very high variance = overly sharp (possible screen moire)
    laplacian_risk = 0.0
    if lap_var < 20:
        laplacian_risk = 0.4   # too smooth
    elif lap_var > 500:
        laplacian_risk = 0.2   # possibly screen artifacts
    else:
        laplacian_risk = 0.0   # normal

    # 2. Edge detection – look for sharp rectangle boundaries (photo frame)
    edges = cv2.Canny(gray, 50, 150)
    edge_pixels = cv2.countNonZero(edges)
    edge_ratio = edge_pixels / (h * w)

    # Very high edge density can indicate screen/texture noise
    edge_risk = 0.0
    if edge_ratio > 0.18:
        edge_risk = 0.35
    elif edge_ratio < 0.01:
        edge_risk = 0.1   # too few edges (very smooth = possibly printed)

    # 3. Histogram analysis – check for flat color distribution (photo print)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist_std = float(np.std(hist))
    # Very low histogram std = flat image (possible photo)
    hist_risk = 0.0
    if hist_std < 500:
        hist_risk = 0.25

    # 4. Check for specular highlights / glare (screen reflection)
    bright_pixels = float(np.sum(gray > 240)) / (h * w)
    glare_risk = 0.0
    if bright_pixels > 0.05:
        glare_risk = 0.2   # possible screen glare

    flags = []
    if laplacian_risk > 0: flags.append('unusual_sharpness')
    if edge_risk > 0:      flags.append('unusual_edge_density')
    if hist_risk > 0:      flags.append('flat_histogram')
    if glare_risk > 0:     flags.append('possible_glare')

    total_risk = min(1.0, laplacian_risk + edge_risk + hist_risk + glare_risk)

    return {
        'risk': total_risk,
        'flags': flags,
        'details': {
            'laplacian_var': round(lap_var, 2),
            'edge_ratio': round(edge_ratio, 4),
            'hist_std': round(hist_std, 2),
            'glare_ratio': round(bright_pixels, 4)
        }
    }


def get_mouth_open_ratio(landmarks):
    """
    Calculate the ratio of mouth opening normalized by eye distance.
    landmarks is a dictionary mapping feature names (e.g. 'left_eye', 'top_lip') 
    to lists of (x, y) coordinates.
    """
    import numpy as np
    
    left_eye = np.array(landmarks['left_eye'])
    right_eye = np.array(landmarks['right_eye'])
    top_lip = np.array(landmarks['top_lip'])
    bottom_lip = np.array(landmarks['bottom_lip'])
    
    # Calculate eye center distance for normalization (scale-invariant)
    left_eye_center = np.mean(left_eye, axis=0)
    right_eye_center = np.mean(right_eye, axis=0)
    eye_distance = np.linalg.norm(left_eye_center - right_eye_center)
    
    if eye_distance == 0:
        return 0.0
        
    # Calculate lip centers distance
    top_lip_center = np.mean(top_lip, axis=0)
    bottom_lip_center = np.mean(bottom_lip, axis=0)
    mouth_distance = np.linalg.norm(top_lip_center - bottom_lip_center)
    
    return float(mouth_distance / eye_distance)
