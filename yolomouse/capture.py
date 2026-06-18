"""Fast screen-region capture via mss.

Create the ScreenCapture inside the thread that uses it: mss handles are
per-thread.
"""
import cv2
import numpy as np
import mss


class ScreenCapture:
    def __init__(self):
        self.sct = mss.mss()

    def grab(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        region = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        raw = self.sct.grab(region)          # BGRA
        arr = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(raw.height, raw.width, 4)
        return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
