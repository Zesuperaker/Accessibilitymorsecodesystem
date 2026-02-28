"""Camera utilities for video capture and processing"""
import cv2
import threading
from flask import current_app


class CameraManager:
    """Manages camera initialization and lifecycle with thread safety"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Implement singleton pattern with thread safety"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.camera = None
                    cls._instance._camera_lock = threading.Lock()
        return cls._instance

    def get_camera(self):
        """Get or initialize camera device

        Returns:
            cv2.VideoCapture: Camera object

        Raises:
            RuntimeError: If no functional camera found
        """
        with self._camera_lock:
            if self.camera is not None and self.camera.isOpened():
                return self.camera

            # Try multiple camera indices
            for i in range(3):
                try:
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        # Set resolution for better performance
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                        # Reduce latency
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        self.camera = cap
                        current_app.logger.info(f"Camera initialized on device {i}")
                        return self.camera
                except Exception as e:
                    current_app.logger.warning(f"Failed to initialize camera {i}: {e}")
                    continue

            error_msg = "Could not find a functional camera. Check permissions and device availability."
            current_app.logger.error(error_msg)
            raise RuntimeError(error_msg)

    def release_camera(self):
        """Release camera resource safely"""
        with self._camera_lock:
            if self.camera is not None:
                try:
                    self.camera.release()
                    current_app.logger.info("Camera released successfully")
                except Exception as e:
                    current_app.logger.error(f"Error releasing camera: {e}")
                finally:
                    self.camera = None

    def is_available(self):
        """Check if camera is available

        Returns:
            bool: True if camera is initialized and open
        """
        with self._camera_lock:
            return self.camera is not None and self.camera.isOpened()

    def reset(self):
        """Reset camera connection (useful for troubleshooting)"""
        self.release_camera()
        # Next call to get_camera() will reinitialize