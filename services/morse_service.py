"""Morse code detection service - handles blink detection and morse decoding"""
import threading
from time import perf_counter
import requests
from flask import current_app

# Morse Binary Tree: Index = (trace - 1)
# dot = move left (2*i), dash = move right (2*i + 1)
MORSE_TREE = [
    '', 'E', 'T', 'I', 'A', 'N', 'M', 'S', 'U', 'R', 'W', 'D', 'K', 'G', 'O',
    'H', 'V', 'F', '', 'L', '', 'P', 'J', 'B', 'X', 'C', 'Y', 'Z', 'Q', '', ''
]


class MorseBlinkDetector:
    """Detects morse code from eye blinks and manages conversation state"""

    def __init__(self):
        """Initialize morse detector with state management"""
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
        """Converts binary signal list into a letter using binary tree trace.

        Returns:
            str: Decoded letter or '?' if invalid
        """
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
        """Reset all state for a fresh start"""
        with self.lock:
            self.current_signals = []
            self.current_word = ''
            self.morse_string = ''
            self.start_flag = False
            self.is_paused = False
            self.chat_history = []

    def get_status(self):
        """Get current decoder status

        Returns:
            dict: Current state of the detector
        """
        with self.lock:
            return {
                'word': self.current_word,
                'morse': self.morse_string,
                'conversation': self.chat_history,
                'active': self.start_flag,
                'paused': self.is_paused,
            }

    def check_and_handle_inactivity(self, inactivity_threshold=5.0):
        """Check for inactivity and auto-reset if threshold exceeded

        Args:
            inactivity_threshold: Seconds of inactivity before auto-reset (default: 5)

        Returns:
            dict: {
                'auto_reset': bool (True if reset occurred),
                'word_before_reset': str (word that was reset)
            }
        """
        with self.lock:
            # Only check if detection is active and not paused
            if not self.start_flag or self.is_paused:
                return {
                    'auto_reset': False,
                    'word_before_reset': ''
                }

            # If no signals detected, no inactivity to check
            if not self.current_word and not self.current_signals:
                return {
                    'auto_reset': False,
                    'word_before_reset': ''
                }

            # Check if inactivity threshold exceeded
            time_since_last_activity = perf_counter() - self.last_blink_end_time

            if time_since_last_activity > inactivity_threshold:
                # Capture word before reset
                word_before_reset = self.current_word

                # Reset state
                self.current_signals = []
                self.current_word = ''
                self.morse_string = ''

                return {
                    'auto_reset': True,
                    'word_before_reset': word_before_reset
                }

            return {
                'auto_reset': False,
                'word_before_reset': ''
            }

    def process_eye_aspect_ratio(self, smooth_ratio, baseline):
        """Process EAR (Eye Aspect Ratio) to detect blinks and morse signals

        Args:
            smooth_ratio: Current smoothed EAR value
            baseline: Baseline EAR for this session
        """
        blink_threshold = 4

        with self.lock:
            if (baseline - smooth_ratio) > blink_threshold:
                # Blink detected
                if not self.is_blinking:
                    self.blink_start_time = perf_counter()
                    self.is_blinking = True
            else:
                # Blink ended
                if self.is_blinking:
                    duration = perf_counter() - self.blink_start_time
                    self.last_blink_end_time = perf_counter()

                    if duration < 0.30:  # Dot
                        self.current_signals.append(0)
                        self.morse_string += "."
                    elif duration < 1.5:  # Dash
                        self.current_signals.append(1)
                        self.morse_string += "_"
                    self.is_blinking = False

                # If 1.2 seconds pass without a blink, finalize the current letter
                if (perf_counter() - self.last_blink_end_time) > 1.2 and self.current_signals:
                    self.current_word += self.decode_signals()
                    self.current_signals = []
                    self.morse_string = ""

    def send_to_ai(self, message):
        """Send message to Mistral AI API (synchronous)

        Args:
            message: User message to send

        Returns:
            dict: Response status and AI message

        Raises:
            ValueError: If API key not configured
            requests.RequestException: If API call fails
        """
        api_key = current_app.config.get('MISTRAL_API_KEY')
        if not api_key:
            return {
                'status': 'error',
                'message': 'MISTRAL_API_KEY not configured'
            }

        self.is_processing = True
        try:
            with self.lock:
                self.chat_history.append({'role': 'user', 'content': message})
                messages_to_send = list(self.chat_history)

            response = requests.post(
                current_app.config.get('MISTRAL_API_URL', 'https://api.mistral.ai/v1/chat/completions'),
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'mistral-large-latest',
                    'messages': messages_to_send
                },
                timeout=10
            )
            response.raise_for_status()

            ai_msg = response.json()['choices'][0]['message']['content']

            with self.lock:
                self.chat_history.append({'role': 'assistant', 'content': ai_msg})
                self.current_word = ""  # Clear word for next input

            return {
                'status': 'success',
                'response': ai_msg
            }
        except requests.exceptions.Timeout:
            return {
                'status': 'error',
                'message': 'API request timed out'
            }
        except requests.exceptions.RequestException as e:
            return {
                'status': 'error',
                'message': f'API error: {str(e)}'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Unexpected error: {str(e)}'
            }
        finally:
            self.is_processing = False