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

        # Detect face locations using HOG-based model (fast, CPU-friendly)
        face_locations = face_recognition.face_locations(image, model='hog')

        # Compute 128-d encodings for every detected face
        encodings = face_recognition.face_encodings(image, known_face_locations=face_locations)

        return encodings, len(encodings)

    except Exception as e:
        print(f'[FaceUtils] Error processing {image_path}: {e}')
        return [], 0


def match_face_encoding(user_encoding: np.ndarray, stored_records: list, threshold: float = 0.5):
    """
    Compare a user's face encoding against a list of stored encodings.

    Args:
        user_encoding:   128-d numpy array of the user's face.
        stored_records:  List of (id, image_path, numpy_encoding) tuples from DB.
        threshold:       Maximum face distance to consider a match (lower = stricter).
                         Default 0.5 is recommended by face_recognition docs.

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
