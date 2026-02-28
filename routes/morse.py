"""Morse code detection routes"""
import io
import cv2
import logging
import numpy as np
from flask import Blueprint, render_template, jsonify, request
from cvzone.FaceMeshModule import FaceMeshDetector

from services.morse_service import MorseBlinkDetector

morse_bp = Blueprint(
    'morse',
    __name__,
    url_prefix='/morse',
    template_folder='../templates/morse'
)

# Initialize state
morse_state = MorseBlinkDetector()

# Lazy-loaded detector
_detector = None
logger = logging.getLogger(__name__)


def get_detector():
    """Get or initialize the face mesh detector"""
    global _detector
    if _detector is None:
        try:
            logger.info("Initializing FaceMeshDetector...")
            _detector = FaceMeshDetector(maxFaces=1)
            logger.info("FaceMeshDetector initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize FaceMeshDetector: {e}")
            raise RuntimeError(f"Failed to initialize face detector: {e}")
    return _detector


@morse_bp.route('/')
def morse_interface():
    """Display morse detection interface"""
    return render_template('morse.html')


@morse_bp.route('/start', methods=['POST'])
def start_detection():
    """Start morse detection"""
    try:
        morse_state.start_flag = True
        logger.info("✅ Morse detection started")
        return jsonify({'status': 'active', 'message': 'Detection started'}), 200
    except Exception as e:
        logger.error(f"Error starting detection: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/toggle_pause', methods=['POST'])
def toggle_pause():
    """Toggle pause state"""
    try:
        morse_state.is_paused = not morse_state.is_paused
        state = 'paused' if morse_state.is_paused else 'resumed'
        logger.info(f"Detection {state}")
        return jsonify({
            'status': state,
            'paused': morse_state.is_paused
        }), 200
    except Exception as e:
        logger.error(f"Error toggling pause: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/reset', methods=['POST'])
def reset():
    """Reset morse decoder and conversation"""
    try:
        morse_state.reset()
        logger.info("🔄 Morse decoder reset")
        return jsonify({'status': 'cleared', 'message': 'Decoder reset'}), 200
    except Exception as e:
        logger.error(f"Error resetting decoder: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/status')
def get_status():
    """Get current detection status"""
    try:
        status = morse_state.get_status()
        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/check_inactivity')
def check_inactivity():
    """Check for inactivity and auto-reset if threshold exceeded"""
    try:
        result = morse_state.check_and_handle_inactivity(inactivity_threshold=5.0)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error checking inactivity: {e}")
        return jsonify({'auto_reset': False, 'word_before_reset': ''}), 500


@morse_bp.route('/send', methods=['POST'])
def send_to_ai():
    """Send detected message to AI"""
    if not morse_state.current_word:
        return jsonify({
            'status': 'error',
            'message': 'No message to send'
        }), 400

    if morse_state.is_processing:
        return jsonify({
            'status': 'error',
            'message': 'Already processing a message'
        }), 400

    try:
        word_to_send = morse_state.current_word
        logger.info(f"📤 Sending to AI: {word_to_send}")

        result = morse_state.send_to_ai(word_to_send)

        status_code = 200 if result['status'] == 'success' else 500
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Error sending to AI: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@morse_bp.route('/process_frame', methods=['POST'])
def process_frame():
    """Process a frame from the client browser

    Receives JPEG frame from getUserMedia video stream,
    performs face detection and eye tracking for morse code detection.

    Returns: JSON status
    """
    try:
        # Get frame from request
        if 'frame' not in request.files:
            return jsonify({'status': 'error', 'message': 'No frame in request'}), 400

        frame_file = request.files['frame']
        frame_data = np.frombuffer(frame_file.read(), np.uint8)
        img = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({'status': 'error', 'message': 'Invalid frame data'}), 400

        # Only process if detection is active and not paused
        if not morse_state.start_flag or morse_state.is_paused:
            return jsonify({'status': 'skipped', 'reason': 'detection_inactive'}), 200

        # Get detector (lazy load)
        try:
            detector = get_detector()
        except RuntimeError as e:
            logger.error(f"Detector error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

        # Detect faces
        try:
            img, faces = detector.findFaceMesh(img, draw=False)
        except Exception as e:
            logger.warning(f"Face detection error: {e}")
            faces = []

        # Process detected faces
        if faces:
            try:
                face = faces[0]

                # Eye landmarks
                # Left Eye: 159 (Top), 23 (Bottom), 130 (Left), 243 (Right)
                # Right Eye: 386 (Top), 374 (Bottom), 398 (Left), 359 (Right)
                v_dist_l, _ = detector.findDistance(face[159], face[23])
                h_dist_l, _ = detector.findDistance(face[130], face[243])
                v_dist_r, _ = detector.findDistance(face[386], face[374])
                h_dist_r, _ = detector.findDistance(face[398], face[359])

                # Calculate Eye Aspect Ratio
                current_ratio = ((v_dist_l / h_dist_l) + (v_dist_r / h_dist_r)) / 2 * 100

                # Smooth the ratio
                morse_state.ratio_history.append(current_ratio)
                if len(morse_state.ratio_history) > 3:
                    morse_state.ratio_history.pop(0)
                smooth_ratio = sum(morse_state.ratio_history) / len(morse_state.ratio_history)

                # Maintain baseline
                morse_state.avg_ratio_history.append(smooth_ratio)
                if len(morse_state.avg_ratio_history) > 150:
                    morse_state.avg_ratio_history.pop(0)
                baseline = sum(morse_state.avg_ratio_history) / len(morse_state.avg_ratio_history)

                # Process the eye aspect ratio
                morse_state.process_eye_aspect_ratio(smooth_ratio, baseline)

                return jsonify({
                    'status': 'processed',
                    'faces_detected': len(faces),
                    'current_word': morse_state.current_word,
                    'current_morse': morse_state.morse_string
                }), 200

            except Exception as e:
                logger.warning(f"Face processing error: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        # No face detected
        return jsonify({
            'status': 'no_faces',
            'current_word': morse_state.current_word,
            'current_morse': morse_state.morse_string
        }), 200

    except Exception as e:
        logger.error(f"❌ Frame processing error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500