"""YoloMouse (Python) entry point.

Run:  python main.py
"""
import ctypes
import threading
import tkinter as tk

from yolomouse.config import Shared
from yolomouse.gui import App
from yolomouse import worker


def _enable_dpi_awareness():
    # Per-monitor-v2 so capture pixels line up with screen pixels.
    # Pass the handle as c_void_p so it isn't truncated on 64-bit.
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def main():
    _enable_dpi_awareness()

    shared = Shared()
    t = threading.Thread(target=worker.run, args=(shared,), daemon=True)
    t.start()

    root = tk.Tk()
    App(root, shared)
    root.mainloop()

    shared.running = False
    t.join(timeout=1.0)


if __name__ == "__main__":
    main()
