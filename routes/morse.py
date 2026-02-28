"""Morse code detection routes"""
import cv2
from flask import Blueprint, render_template, Response, jsonify
from cvzone.FaceMeshModule import FaceMeshDetector

from services.morse_service import MorseBlinkDetector
from utils import CameraManager

morse_bp = Blueprint(
    'morse',
    __name__,
    url_prefix='/morse',
    template_folder='../templates/morse'
)

# Initialize state and camera manager
morse_state = MorseBlinkDetector()
camera_manager = CameraManager()

# Lazy-loaded detector (initialized on first use, not at import)
_detector = None

def get_detector():
    """Get or initialize the face mesh detector (lazy loading)

    This is called only when video processing starts, not at module import.
    Prevents initialization errors if mediapipe isn't ready.

    Returns:
        FaceMeshDetector: Face detection instance
    """
    global _detector
    if _detector is None:
        try:
            _detector = FaceMeshDetector(maxFaces=1)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize FaceMeshDetector: {e}")
    return _detector


@morse_bp.route('/')
def morse_interface():
    """Display morse detection interface"""
    return render_template('morse.html')


@morse_bp.route('/start', methods=['POST'])
def start_detection():
    """Start morse detection

    Returns:
        JSON: Status response
    """
    try:
        morse_state.start_flag = True
        return jsonify({'status': 'active', 'message': 'Detection started'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/pause', methods=['POST'])
def toggle_pause():
    """Toggle pause state

    Returns:
        JSON: Current pause state
    """
    try:
        morse_state.is_paused = not morse_state.is_paused
        return jsonify({
            'status': 'paused' if morse_state.is_paused else 'resumed',
            'paused': morse_state.is_paused
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/reset', methods=['POST'])
def reset():
    """Reset morse decoder and conversation

    Returns:
        JSON: Status response
    """
    try:
        morse_state.reset()
        return jsonify({'status': 'cleared', 'message': 'Decoder reset'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/status')
def get_status():
    """Get current detection status

    Returns:
        JSON: Current morse state and conversation history
    """
    try:
        status = morse_state.get_status()
        return jsonify(status), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/send', methods=['POST'])
def send_to_ai():
    """Send detected message to AI

    Returns:
        JSON: AI response or error
    """
    if not morse_state.current_word or morse_state.is_processing:
        return jsonify({
            'status': 'error',
            'message': 'No message to send or already processing'
        }), 400

    try:
        # Using synchronous call - in production, consider using async/celery
        result = morse_state.send_to_ai(morse_state.current_word)
        status_code = 200 if result['status'] == 'success' else 500
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def _process_frame():
    """Process video frames for morse detection

    Yields:
        bytes: JPEG encoded frame with boundaries for streaming
    """
    try:
        detector = get_detector()  # ← LAZY LOAD DETECTOR HERE
        camera = camera_manager.get_camera()
    except RuntimeError as e:
        print(f"Initialization error: {e}")
        return

    while True:
        try:
            success, img = camera.read()
            if not success:
                break

            img, faces = detector.findFaceMesh(img, draw=False)

            if faces and morse_state.start_flag and not morse_state.is_paused:
                face = faces[0]

                # Extract landmarks for EAR (Eye Aspect Ratio) calculation
                # Left Eye: 159 (Top), 23 (Bottom), 130 (Left), 243 (Right)
                # Right Eye: 386 (Top), 374 (Bottom), 398 (Left), 359 (Right)
                v_dist_l, _ = detector.findDistance(face[159], face[23])
                h_dist_l, _ = detector.findDistance(face[130], face[243])
                v_dist_r, _ = detector.findDistance(face[386], face[374])
                h_dist_r, _ = detector.findDistance(face[398], face[359])

                # Calculate averaged Eye Aspect Ratio (EAR)
                current_ratio = ((v_dist_l / h_dist_l) + (v_dist_r / h_dist_r)) / 2 * 100

                # Smoothing EAR values
                morse_state.ratio_history.append(current_ratio)
                if len(morse_state.ratio_history) > 3:
                    morse_state.ratio_history.pop(0)
                smooth_ratio = sum(morse_state.ratio_history) / len(morse_state.ratio_history)

                # Maintain a longer average for baseline comparison
                morse_state.avg_ratio_history.append(smooth_ratio)
                if len(morse_state.avg_ratio_history) > 150:
                    morse_state.avg_ratio_history.pop(0)
                baseline = sum(morse_state.avg_ratio_history) / len(morse_state.avg_ratio_history)

                # Process eye aspect ratio for blink detection
                morse_state.process_eye_aspect_ratio(smooth_ratio, baseline)

            # Visual Overlays
            if morse_state.is_paused:
                cv2.putText(img, "PAUSED", (50, 50), cv2.FONT_HERSHEY_SIMPLEX,
                           1, (0, 0, 255), 2)

            _, buffer = cv2.imencode('.jpg', img)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        except Exception as e:
            print(f"Frame processing error: {e}")
            break


@morse_bp.route('/video_feed')
def video_feed():
    """Stream video frames for display

    Returns:
        Response: MJPEG stream
    """
    return Response(
        _process_frame(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )