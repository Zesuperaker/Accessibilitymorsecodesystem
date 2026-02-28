"""Camera utilities for video capture and processing"""
import cv2
from flask import current_app


class CameraManager:
    """Manages camera initialization and lifecycle"""

    _instance = None
    _lock = None

    def __new__(cls):
        """Implement singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.camera = None
        return cls._instance

    def get_camera(self):
        """Get or initialize camera device

        Returns:
            cv2.VideoCapture: Camera object

        Raises:
            RuntimeError: If no functional camera found
        """
        if self.camera is not None:
            return self.camera

        for i in range(3):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.camera = cap
                current_app.logger.info(f"Camera initialized on device {i}")
                return self.camera

        raise RuntimeError("Could not find a functional camera.")

    def release_camera(self):
        """Release camera resource"""
        if self.camera is not None:
            self.camera.release()
            self.camera = None
            current_app.logger.info("Camera released")

    def is_available(self):
        """Check if camera is available

        Returns:
            bool: True if camera is initialized and open
        """
        return self.camera is not None and self.camera.isOpened()