"""
LSOYS AI Monitoring — Live Demo Application
=============================================
A simple Flask app for real-time face detection, recognition,
talking detection, and warning system using your webcam.

Run: python app.py
Open: http://127.0.0.1:5000
"""
import os
import cv2
import json
import time
import pickle
import base64
import threading
import numpy as np
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify, Response, redirect, url_for
)

# ── Try importing face_recognition (optional, needs dlib) ──
try:
    import face_recognition
    USE_FACE_RECOGNITION = True
    print("[OK] face_recognition library loaded — using dlib-based detection")
except ImportError:
    USE_FACE_RECOGNITION = False
    print("[INFO] face_recognition not found — using OpenCV fallback")
    print("       Install with: pip install face-recognition (requires dlib + CMake)")

# ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'lsoys-demo-secret-key'

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
FACES_DIR = os.path.join(DATA_DIR, 'faces')
ENCODINGS_FILE = os.path.join(DATA_DIR, 'encodings.pkl')
LOGS_FILE = os.path.join(DATA_DIR, 'logs.json')

os.makedirs(FACES_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ── Global State ──
camera = None
camera_lock = threading.Lock()
is_monitoring = False
monitoring_thread = None

# Known faces
known_encodings = []
known_names = []

# Warning tracking: {name: warning_count}
warnings = {}

# Event logs
logs = []

# Latest processed frame (JPEG bytes) for streaming
latest_frame = None
frame_lock = threading.Lock()

# Detected faces info for the UI
detected_info = []
info_lock = threading.Lock()

# Talking state
talking_active = False
talking_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════
#  FACE ENCODING / RECOGNITION
# ══════════════════════════════════════════════════════════════

def load_encodings():
    """Load saved face encodings from disk."""
    global known_encodings, known_names
    if os.path.exists(ENCODINGS_FILE):
        with open(ENCODINGS_FILE, 'rb') as f:
            data = pickle.load(f)
            known_encodings = data.get('encodings', [])
            known_names = data.get('names', [])
    print(f"[OK] Loaded {len(known_names)} known face(s)")


def save_encodings():
    """Save face encodings to disk."""
    with open(ENCODINGS_FILE, 'wb') as f:
        pickle.dump({'encodings': known_encodings, 'names': known_names}, f)


def encode_face(image_path):
    """Generate face encoding from an image file."""
    if USE_FACE_RECOGNITION:
        img = face_recognition.load_image_file(image_path)
        encs = face_recognition.face_encodings(img)
        return encs[0] if encs else None
    else:
        # OpenCV fallback: flatten grayscale face region as a simple descriptor
        img = cv2.imread(image_path)
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        faces = cascade.detectMultiScale(gray, 1.3, 5)
        if len(faces) == 0:
            # Try using the whole image as the face
            face_roi = cv2.resize(gray, (100, 100))
        else:
            x, y, w, h = faces[0]
            face_roi = cv2.resize(gray[y:y+h, x:x+w], (100, 100))
        return face_roi.flatten().astype(np.float64)


def recognize_faces(frame):
    """Detect and recognize faces in a frame."""
    results = []

    if USE_FACE_RECOGNITION:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
        locations = face_recognition.face_locations(small, model='hog')
        encodings = face_recognition.face_encodings(small, locations)

        for enc, loc in zip(encodings, locations):
            top, right, bottom, left = [v * 2 for v in loc]
            name = "Unknown"
            confidence = 0.0

            if known_encodings:
                distances = face_recognition.face_distance(known_encodings, enc)
                best_idx = np.argmin(distances)
                if distances[best_idx] < 0.55:
                    name = known_names[best_idx]
                    confidence = round((1.0 - distances[best_idx]) * 100, 1)

            results.append({
                'name': name,
                'confidence': confidence,
                'box': (left, top, right - left, bottom - top),
            })
    else:
        # OpenCV Haar cascade fallback
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))

        for (x, y, w, h) in faces:
            name = "Unknown"
            confidence = 0.0

            if known_encodings:
                roi = cv2.resize(gray[y:y+h, x:x+w], (100, 100))
                descriptor = roi.flatten().astype(np.float64)

                best_dist = float('inf')
                best_idx = -1
                for i, enc in enumerate(known_encodings):
                    dist = np.linalg.norm(descriptor - enc)
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = i

                threshold = 4500.0
                if best_dist < threshold and best_idx >= 0:
                    name = known_names[best_idx]
                    confidence = round(max(0, (1.0 - best_dist / threshold)) * 100, 1)

            results.append({
                'name': name,
                'confidence': confidence,
                'box': (int(x), int(y), int(w), int(h)),
            })

    return results


# ══════════════════════════════════════════════════════════════
#  WARNING SYSTEM
# ══════════════════════════════════════════════════════════════

WARNING_MESSAGES = {
    1: "Please maintain silence",
    2: "Final warning!",
    3: "Please leave the room",
}


def issue_warning(name):
    """Issue a warning for a person detected talking."""
    if name == "Unknown":
        return None

    count = warnings.get(name, 0) + 1
    warnings[name] = count

    level = min(count, 3)
    message = WARNING_MESSAGES[level]

    log_entry = {
        'name': name,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'event': f"Warning {level}: {message}",
        'level': level,
    }
    logs.append(log_entry)
    save_logs()

    return {
        'name': name,
        'level': level,
        'count': count,
        'message': message,
    }


def save_logs():
    """Persist logs to file."""
    try:
        with open(LOGS_FILE, 'w') as f:
            json.dump(logs[-500:], f, indent=2)
    except Exception:
        pass


def load_logs():
    """Load logs from file."""
    global logs
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, 'r') as f:
                logs = json.load(f)
        except Exception:
            logs = []


# ══════════════════════════════════════════════════════════════
#  CAMERA & MONITORING
# ══════════════════════════════════════════════════════════════

def start_camera():
    """Open the webcam."""
    global camera
    with camera_lock:
        if camera is not None:
            return True
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            camera = None
            return False
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return True


def stop_camera():
    """Release the webcam."""
    global camera, is_monitoring
    is_monitoring = False
    with camera_lock:
        if camera:
            camera.release()
            camera = None


def monitoring_loop():
    """Background thread: capture frames, detect faces, apply rules."""
    global latest_frame, detected_info, is_monitoring, talking_active

    frame_count = 0
    last_warning_time = {}

    while is_monitoring:
        with camera_lock:
            if camera is None or not camera.isOpened():
                time.sleep(0.1)
                continue
            ret, frame = camera.read()

        if not ret:
            time.sleep(0.05)
            continue

        frame_count += 1
        annotated = frame.copy()

        # Process every 3rd frame for performance
        if frame_count % 3 == 0:
            results = recognize_faces(frame)

            with info_lock:
                detected_info = results

            # Check if talking is active
            with talking_lock:
                is_talking = talking_active

            for r in results:
                x, y, w, h = r['box']
                name = r['name']
                conf = r['confidence']

                # Draw box
                if name != "Unknown":
                    color = (0, 255, 0)  # Green for recognized
                    label = f"{name} ({conf}%)"
                else:
                    color = (0, 0, 255)  # Red for unknown
                    label = "Unknown"

                # Check warning level for coloring
                w_count = warnings.get(name, 0)
                if w_count >= 3:
                    color = (0, 0, 255)  # Red — expelled
                elif w_count >= 2:
                    color = (0, 128, 255)  # Orange — final warning
                elif w_count >= 1:
                    color = (0, 255, 255)  # Yellow — first warning

                cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
                cv2.putText(annotated, label, (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                # If talking detected, issue warning to closest/first recognized face
                if is_talking and name != "Unknown":
                    now = time.time()
                    last_t = last_warning_time.get(name, 0)
                    if now - last_t > 5:  # 5 second cooldown per person
                        issue_warning(name)
                        last_warning_time[name] = now

                # Show warning banner on frame
                if w_count > 0 and name != "Unknown":
                    msg = WARNING_MESSAGES.get(min(w_count, 3), "")
                    banner_color = (0, 0, 200) if w_count >= 3 else (0, 165, 255)
                    cv2.putText(annotated, f"W{w_count}: {msg}", (x, y + h + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, banner_color, 2)

            # Reset talking flag
            with talking_lock:
                talking_active = False

        # Encode frame to JPEG
        ret, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ret:
            with frame_lock:
                latest_frame = jpeg.tobytes()

        time.sleep(0.03)  # ~30 FPS


def generate_frames():
    """MJPEG stream generator."""
    while True:
        with frame_lock:
            frame = latest_frame
        if frame:
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
            )
        time.sleep(0.05)


# ══════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return redirect(url_for('upload_page'))


@app.route('/upload', methods=['GET'])
def upload_page():
    """Face upload page."""
    # Get list of registered people
    people = {}
    for name in set(known_names):
        count = known_names.count(name)
        person_dir = os.path.join(FACES_DIR, name.replace(' ', '_'))
        images = []
        if os.path.exists(person_dir):
            images = [f for f in os.listdir(person_dir) if f.endswith(('.jpg', '.png', '.jpeg'))]
        people[name] = {'encodings': count, 'images': len(images)}
    return render_template('upload.html', people=people)


@app.route('/upload', methods=['POST'])
def upload_face():
    """Handle face image upload."""
    name = request.form.get('name', '').strip()
    files = request.files.getlist('images')

    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if not files or files[0].filename == '':
        return jsonify({'error': 'At least one image is required'}), 400

    person_dir = os.path.join(FACES_DIR, name.replace(' ', '_'))
    os.makedirs(person_dir, exist_ok=True)

    success_count = 0
    for f in files:
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png'):
                continue
            filename = f"{name.replace(' ', '_')}_{int(time.time())}_{success_count}{ext}"
            filepath = os.path.join(person_dir, filename)
            f.save(filepath)

            # Generate encoding
            encoding = encode_face(filepath)
            if encoding is not None:
                known_encodings.append(encoding)
                known_names.append(name)
                success_count += 1

    if success_count > 0:
        save_encodings()
        return jsonify({
            'success': True,
            'message': f'Added {success_count} face(s) for {name}',
            'total_known': len(known_names),
        })
    else:
        return jsonify({'error': 'No faces detected in uploaded images'}), 400


@app.route('/delete/<name>', methods=['POST'])
def delete_person(name):
    """Remove a person's face data."""
    global known_encodings, known_names

    # Remove encodings
    indices = [i for i, n in enumerate(known_names) if n == name]
    known_encodings = [e for i, e in enumerate(known_encodings) if i not in indices]
    known_names = [n for i, n in enumerate(known_names) if i not in indices]
    save_encodings()

    # Remove images
    person_dir = os.path.join(FACES_DIR, name.replace(' ', '_'))
    if os.path.exists(person_dir):
        import shutil
        shutil.rmtree(person_dir)

    # Reset warnings
    warnings.pop(name, None)

    return jsonify({'success': True, 'message': f'Removed {name}'})


@app.route('/live')
def live_page():
    """Live camera monitoring page."""
    return render_template('live.html',
                           known_count=len(set(known_names)),
                           is_monitoring=is_monitoring)


@app.route('/video_feed')
def video_feed():
    """MJPEG video stream endpoint."""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    """Start the camera and monitoring loop."""
    global is_monitoring, monitoring_thread

    if is_monitoring:
        return jsonify({'status': 'Already monitoring'})

    if not start_camera():
        return jsonify({'error': 'Cannot open webcam'}), 500

    is_monitoring = True
    monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitoring_thread.start()

    return jsonify({'status': 'Monitoring started'})


@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """Stop monitoring."""
    stop_camera()
    return jsonify({'status': 'Monitoring stopped'})


@app.route('/talking', methods=['POST'])
def report_talking():
    """Receive talking detection from browser audio."""
    global talking_active
    with talking_lock:
        talking_active = True
    return jsonify({'status': 'ok'})


@app.route('/status')
def get_status():
    """Get current monitoring status and detected faces."""
    with info_lock:
        faces = list(detected_info)
    return jsonify({
        'is_monitoring': is_monitoring,
        'detected_faces': faces,
        'warnings': dict(warnings),
        'known_count': len(set(known_names)),
    })


@app.route('/logs')
def logs_page():
    """Logs page."""
    return render_template('logs.html', logs=list(reversed(logs)))


@app.route('/api/logs')
def api_logs():
    """Get logs as JSON."""
    return jsonify(list(reversed(logs[-100:])))


@app.route('/reset_warnings', methods=['POST'])
def reset_warnings():
    """Reset all warnings."""
    warnings.clear()
    return jsonify({'status': 'Warnings reset'})


# ══════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    load_encodings()
    load_logs()
    print("\n" + "=" * 50)
    print("  LSOYS AI Monitoring — Live Demo")
    print("=" * 50)
    print(f"  Known faces: {len(set(known_names))}")
    print(f"  Face recognition: {'dlib (high accuracy)' if USE_FACE_RECOGNITION else 'OpenCV (fallback)'}")
    print(f"  Open: http://127.0.0.1:5000")
    print("=" * 50 + "\n")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
