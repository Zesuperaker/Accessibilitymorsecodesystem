/**
 * Text-to-Speech Module
 * Uses browser's Web Speech API for voice output
 * No external dependencies or API keys required
 */

class TextToSpeech {
    constructor(options = {}) {
        // Get the appropriate speech synthesis API
        this.synth = window.speechSynthesis;

        // Configuration
        this.rate = options.rate || 1.0;        // 0.1 to 10
        this.pitch = options.pitch || 1.0;      // 0 to 2
        this.volume = options.volume || 1.0;    // 0 to 1
        this.language = options.language || 'en-US';

        // State tracking
        this.isSpeaking = false;
        this.isPaused = false;

        // Callbacks
        this.onStart = options.onStart || (() => {});
        this.onEnd = options.onEnd || (() => {});
        this.onError = options.onError || (() => {});
    }

    /**
     * Speak the provided text
     * @param {string} text - Text to speak
     * @returns {boolean} - True if speech started, false if already speaking
     */
    speak(text) {
        if (!text || text.trim() === '') {
            console.warn('TTS: No text provided');
            return false;
        }

        // Cancel any ongoing speech
        if (this.isSpeaking) {
            this.synth.cancel();
        }

        const utterance = new SpeechSynthesisUtterance(text);

        // Set properties
        utterance.rate = this.rate;
        utterance.pitch = this.pitch;
        utterance.volume = this.volume;
        utterance.lang = this.language;

        // Set up event handlers
        utterance.onstart = () => {
            this.isSpeaking = true;
            this.isPaused = false;
            this.onStart();
        };

        utterance.onend = () => {
            this.isSpeaking = false;
            this.isPaused = false;
            this.onEnd();
        };

        utterance.onerror = (event) => {
            this.isSpeaking = false;
            console.error('TTS Error:', event.error);
            this.onError(event.error);
        };

        // Speak the text
        this.synth.speak(utterance);
        return true;
    }

    /**
     * Pause speech (if supported)
     */
    pause() {
        if (this.isSpeaking && this.synth.pause) {
            this.synth.pause();
            this.isPaused = true;
        }
    }

    /**
     * Resume speech (if supported)
     */
    resume() {
        if (this.isPaused && this.synth.resume) {
            this.synth.resume();
            this.isPaused = false;
        }
    }

    /**
     * Stop all speech
     */
    stop() {
        this.synth.cancel();
        this.isSpeaking = false;
        this.isPaused = false;
    }

    /**
     * Check if TTS is available in the browser
     * @returns {boolean}
     */
    static isSupported() {
        return 'speechSynthesis' in window;
    }

    /**
     * Get available voices
     * @returns {array} - Array of available voice objects
     */
    static getAvailableVoices() {
        return window.speechSynthesis.getVoices();
    }

    /**
     * Set voice by index or name
     * @param {number|string} voiceIdentifier - Index or name of voice
     */
    setVoice(voiceIdentifier) {
        const voices = TextToSpeech.getAvailableVoices();

        if (typeof voiceIdentifier === 'number') {
            // By index
            if (voiceIdentifier >= 0 && voiceIdentifier < voices.length) {
                this.voice = voices[voiceIdentifier];
            }
        } else if (typeof voiceIdentifier === 'string') {
            // By name
            const voice = voices.find(v =>
                v.name.toLowerCase().includes(voiceIdentifier.toLowerCase())
            );
            if (voice) {
                this.voice = voice;
            }
        }
    }
}

// Export for use in other modules (if using modules)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TextToSpeech;
}