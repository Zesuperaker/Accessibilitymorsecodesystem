"""Morse code detection routes"""
import cv2
import logging
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
logger = logging.getLogger(__name__)


def get_detector():
    """Get or initialize the face mesh detector (lazy loading)

    This is called only when video processing starts, not at module import.
    Prevents initialization errors if mediapipe isn't ready.

    Returns:
        FaceMeshDetector: Face detection instance

    Raises:
        RuntimeError: If detector initialization fails
    """
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
    """Start morse detection

    Returns:
        JSON: Status response
    """
    try:
        morse_state.start_flag = True
        logger.info("Morse detection started")
        return jsonify({'status': 'active', 'message': 'Detection started'}), 200
    except Exception as e:
        logger.error(f"Error starting detection: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/toggle_pause', methods=['POST'])
def toggle_pause():
    """Toggle pause state

    Returns:
        JSON: Current pause state
    """
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
    """Reset morse decoder and conversation

    Returns:
        JSON: Status response
    """
    try:
        morse_state.reset()
        logger.info("Morse decoder reset")
        return jsonify({'status': 'cleared', 'message': 'Decoder reset'}), 200
    except Exception as e:
        logger.error(f"Error resetting decoder: {e}")
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
        logger.error(f"Error getting status: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@morse_bp.route('/send', methods=['POST'])
def send_to_ai():
    """Send detected message to AI

    Returns:
        JSON: AI response or error
    """
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
        logger.info(f"Sending to AI: {word_to_send}")

        # Call synchronous send_to_ai method
        result = morse_state.send_to_ai(word_to_send)

        status_code = 200 if result['status'] == 'success' else 500
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Error sending to AI: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def _process_frame():
    """Process video frames for morse detection

    Yields:
        bytes: JPEG encoded frame with boundaries for streaming
    """
    detector = None
    camera = None

    try:
        # Initialize detector and camera
        detector = get_detector()
        camera = camera_manager.get_camera()
        logger.info("Starting frame processing")
    except RuntimeError as e:
        logger.error(f"Initialization failed: {e}")
        # Return error frame
        error_img = None
        try:
            import os
            if os.path.exists('static/error.png'):
                error_img = cv2.imread('static/error.png')
        except:
            pass

        if error_img is None:
            # Create a blank image with error text
            error_img = cv2.zeros((720, 1280, 3), cv2.CV_8UC3)
            cv2.putText(error_img, "Camera/Detector Initialization Failed", (100, 360),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(error_img, str(e), (100, 400),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 1)
        _, buffer = cv2.imencode('.jpg', error_img)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        return

    try:
        frame_count = 0
        while True:
            try:
                success, img = camera.read()
                if not success:
                    logger.warning("Failed to read frame from camera")
                    break

                frame_count += 1

                # Find face mesh
                try:
                    img, faces = detector.findFaceMesh(img, draw=False)
                except Exception as e:
                    logger.warning(f"Face detection error on frame {frame_count}: {e}")
                    faces = []

                # Process faces if detection is active
                if faces and morse_state.start_flag and not morse_state.is_paused:
                    try:
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
                    except Exception as e:
                        logger.warning(f"Error processing face data: {e}")

                # Visual Overlays
                if morse_state.is_paused:
                    cv2.putText(img, "PAUSED", (50, 50), cv2.FONT_HERSHEY_SIMPLEX,
                               1, (0, 0, 255), 2)

                # Encode frame
                _, buffer = cv2.imencode('.jpg', img)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

            except Exception as e:
                logger.error(f"Error processing frame: {e}")
                # Try to continue instead of breaking
                continue

    except Exception as e:
        logger.error(f"Fatal frame processing error: {e}")
    finally:
        if camera is not None:
            camera_manager.release_camera()
            logger.info("Camera released after frame processing")


@morse_bp.route('/video_feed')
def video_feed():
    """Stream video frames for display

    Returns:
        Response: MJPEG stream
    """
    try:
        return Response(
            _process_frame(),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )
    except Exception as e:
        logger.error(f"Error in video feed: {e}")
        return jsonify({'error': str(e)}), 500