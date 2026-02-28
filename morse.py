import os
import requests
import cv2
import cvzone
import threading
from time import perf_counter
from flask import Flask, render_template, Response, jsonify
from cvzone.FaceMeshModule import FaceMeshDetector

# ------------------------------
# Configuration & Constants
# ------------------------------
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_API_KEY = "your_key_here" # It's best to use os.getenv("MISTRAL_API_KEY")

# Morse Binary Tree: Index = (trace - 1)
# dot = move left (2*i), dash = move right (2*i + 1)
MORSE_TREE = [
    '', 'E', 'T', 'I', 'A', 'N', 'M', 'S', 'U', 'R', 'W', 'D', 'K', 'G', 'O', 
    'H', 'V', 'F', '', 'L', '', 'P', 'J', 'B', 'X', 'C', 'Y', 'Z', 'Q', '', ''
]

class MorseBlinkDetector:
    def __init__(self):
        # State Management
        self.lock = threading.Lock()
        self.start_flag = False
        self.is_paused = False
        self.is_processing = False
        
        # Decoding Buffers
        self.current_signals = []  # Binary signals: 0 for dot, 1 for dash
        self.current_word = ''     # Decoded string
        self.morse_string = ''     # Visual string e.g. "._."
        self.chat_history = []
        
        # Blink Timing
        self.blink_start_time = 0
        self.last_blink_end_time = 0
        self.is_blinking = False
        
        # Signal Smoothing (Ratios)
        self.ratio_history = []
        self.avg_ratio_history = []

    def decode_signals(self):
        """Converts binary signal list into a letter using binary tree trace."""
        if not self.current_signals:
            return ''
        if len(self.current_signals) > 4:
            return '?'
        
        trace = 1
        for signal in self.current_signals:
            trace = (2 * trace) + signal
        
        try:
            return MORSE_TREE[int(trace - 1)]
        except IndexError:
            return '?'

    def reset(self):
        with self.lock:
            self.current_signals = []
            self.current_word = ''
            self.morse_string = ''
            self.start_flag = False
            self.is_paused = False
            self.chat_history = []

# ------------------------------
# Camera Initialization
# ------------------------------
def get_camera():
    for i in range(3):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            return cap
    raise RuntimeError("Could not find a functional camera.")

# Global Instances
app = Flask(__name__)
detector = FaceMeshDetector(maxFaces=1)
state = MorseBlinkDetector()
camera = get_camera()

# ------------------------------
# Video Processing Logic
# ------------------------------

def process_frame():
    while True:
        success, img = camera.read()
        if not success: break

        img, faces = detector.findFaceMesh(img, draw=False)
        
        if faces and state.start_flag and not state.is_paused:
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
            state.ratio_history.append(current_ratio)
            if len(state.ratio_history) > 3: state.ratio_history.pop(0)
            smooth_ratio = sum(state.ratio_history) / len(state.ratio_history)

            # Maintain a longer average for baseline comparison
            state.avg_ratio_history.append(smooth_ratio)
            if len(state.avg_ratio_history) > 150: state.avg_ratio_history.pop(0)
            baseline = sum(state.avg_ratio_history) / len(state.avg_ratio_history)

            # Blink Detection Logic
            with state.lock:
                if (baseline - smooth_ratio) > 4: # Threshold for blink
                    if not state.is_blinking:
                        state.blink_start_time = perf_counter()
                        state.is_blinking = True
                else:
                    if state.is_blinking:
                        duration = perf_counter() - state.blink_start_time
                        state.last_blink_end_time = perf_counter()
                        
                        if duration < 0.30: # Dot
                            state.current_signals.append(0)
                            state.morse_string += "."
                        elif duration < 1.5: # Dash
                            state.current_signals.append(1)
                            state.morse_string += "_"
                        state.is_blinking = False

                    # If 1.2 seconds pass without a blink, finalize the current letter
                    if (perf_counter() - state.last_blink_end_time) > 1.2 and state.current_signals:
                        state.current_word += state.decode_signals()
                        state.current_signals = []
                        state.morse_string = ""

        # Visual Overlays
        if state.is_paused:
            cv2.putText(img, "PAUSED", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        _, buffer = cv2.imencode('.jpg', img)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# ------------------------------
# Flask API Routes
# ------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_detection():
    state.start_flag = True
    return jsonify({'status': 'active'})

@app.route('/toggle_pause', methods=['POST'])
def toggle_pause():
    state.is_paused = not state.is_paused
    return jsonify({'status': 'paused' if state.is_paused else 'resumed'})

@app.route('/reset', methods=['POST'])
def reset():
    state.reset()
    return jsonify({'status': 'cleared'})

@app.route('/get_current_message')
def get_status():
    return jsonify({
        'word': state.current_word,
        'morse': state.morse_string,
        'conversation': state.chat_history
    })

@app.route('/process_message', methods=['POST'])
def send_to_ai():
    if not state.current_word or state.is_processing:
        return jsonify({'status': 'error', 'message': 'Invalid state'})

    state.is_processing = True
    state.chat_history.append({'role': 'user', 'content': state.current_word})

    try:
        response = requests.post(
            MISTRAL_API_URL,
            headers={'Authorization': f'Bearer {MISTRAL_API_KEY}', 'Content-Type': 'application/json'},
            json={'model': 'mistral-large-latest', 'messages': state.chat_history},
            timeout=10
        )
        response.raise_for_status()
        ai_msg = response.json()['choices'][0]['message']['content']
        state.chat_history.append({'role': 'assistant', 'content': ai_msg})
        state.current_word = "" # Clear word for next input
        return jsonify({'status': 'success', 'response': ai_msg})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        state.is_processing = False

@app.route('/video_feed')
def video_feed():
    return Response(process_frame(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)