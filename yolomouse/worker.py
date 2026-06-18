"""Worker thread: capture -> detect -> pick target -> smooth -> move.

Runs the closed loop on its own thread so the GUI stays responsive. It only
touches the GUI through the Shared object (guarded by a lock).
"""
import ctypes
import math
import time

import cv2

from .capture import ScreenCapture
from .detector import Detector
from .backends import WindowsMouseBackend, SerialMouseBackend

_user32 = ctypes.windll.user32


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_cursor():
    p = _POINT()
    _user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def key_down(vk):
    return (_user32.GetAsyncKeyState(vk) & 0x8000) != 0


def screen_size():
    return _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def run(shared):
    cap = ScreenCapture()
    det = Detector()
    win_mouse = WindowsMouseBackend()
    ser_mouse = SerialMouseBackend()

    ema = None
    acc_x = acc_y = 0.0
    toggle_state = False
    prev_key = False
    was_in_deadzone = False
    frames = 0
    fps_clock = time.perf_counter()

    while shared.running:
        tick_start = time.perf_counter()
        s = shared.snapshot_settings()

        # ---- handle GUI commands ----
        if shared.do_load:
            shared.do_load = False
            path = shared.model_path
            shared.status = "Loading model..."
            ok, msg = det.load(path, s.use_gpu)
            shared.model_loaded = ok
            shared.provider = det.provider
            shared.status = msg
        if shared.do_connect:
            shared.do_connect = False
            port = shared.port
            ok = ser_mouse.connect(port)
            shared.serial_connected = ok
            shared.serial_verified = ser_mouse.verified
            if ok and ser_mouse.verified:
                shared.status = f"Connected + verified on {port}"
            elif ok:
                shared.status = f"Opened {port} (no firmware reply - check sketch)"
            else:
                shared.status = f"Failed to open {port}"
        if shared.do_disconnect:
            shared.do_disconnect = False
            ser_mouse.disconnect()
            shared.serial_connected = False
            shared.serial_verified = False
            shared.status = "Serial disconnected"

        mouse = ser_mouse if s.backend == "serial" else win_mouse

        # ---- capture region ----
        scr_w, scr_h = screen_size()
        if s.full_screen:
            rx, ry, rw, rh = 0, 0, scr_w, scr_h
        else:
            rw = rh = _clamp(s.fov_size, 64, min(scr_w, scr_h))
            rx = scr_w // 2 - rw // 2
            ry = scr_h // 2 - rh // 2

        try:
            frame = cap.grab(rx, ry, rw, rh)
        except Exception:
            frame = None

        # ---- detect ----
        dets = det.infer(frame, s.conf) if (frame is not None and det.loaded) else []
        shared.det_count = len(dets)

        # ---- choose target (screen coords) ----
        target = None
        if dets:
            cx, cy = get_cursor()
            if s.target_mode == "center":
                ref = (scr_w / 2, scr_h / 2)
            else:
                ref = (cx, cy)

            best = None
            best_metric = float("inf")
            for d in dets:
                ox = rx + d[0] + d[2] * 0.5
                oy = ry + d[1] + d[3] * 0.5
                if s.target_mode == "score":
                    metric = -d[4]
                else:
                    metric = (ox - ref[0]) ** 2 + (oy - ref[1]) ** 2
                if metric < best_metric:
                    best_metric = metric
                    best = (ox, oy)
            target = best

        # ---- EMA jitter filter on the target point ----
        if target is not None:
            if ema is None:
                ema = list(target)
            else:
                a = _clamp(s.target_ema, 0.0, 0.95)
                ema[0] = a * ema[0] + (1 - a) * target[0]
                ema[1] = a * ema[1] + (1 - a) * target[1]
        else:
            ema = None

        # ---- activation ----
        kd = key_down(s.activation_vk)
        if s.activation == "always":
            act = True
        elif s.activation == "toggle":
            if kd and not prev_key:
                toggle_state = not toggle_state
            act = toggle_state
        else:  # hold
            act = kd
        prev_key = kd
        act = act and shared.mover_enabled and (ema is not None) and mouse.ok()
        shared.active = act

        # ---- smoothing / movement ----
        if act:
            cx, cy = get_cursor()
            dx = ema[0] - cx
            dy = ema[1] - cy
            dist = math.hypot(dx, dy)
            if dist <= s.deadzone:
                if s.click_on_target and not was_in_deadzone:
                    mouse.click(0)
                was_in_deadzone = True
                acc_x = acc_y = 0.0
            else:
                was_in_deadzone = False
                step = (1.0 - _clamp(s.smoothing, 0.0, 0.99)) * s.gain
                mvx = dx * step
                mvy = dy * step
                mlen = math.hypot(mvx, mvy)
                if mlen > s.max_speed:
                    k = s.max_speed / mlen
                    mvx *= k
                    mvy *= k
                mvx += acc_x
                mvy += acc_y
                imx = int(mvx)          # truncates toward zero
                imy = int(mvy)
                acc_x = mvx - imx       # carry sub-pixel remainder
                acc_y = mvy - imy
                if imx or imy:
                    mouse.move_relative(imx, imy)
        else:
            acc_x = acc_y = 0.0
            was_in_deadzone = False

        # ---- preview (downscaled RGB with boxes) ----
        if shared.preview_enabled and frame is not None:
            vis = frame.copy()
            for d in dets:
                x, y, w, h = int(d[0]), int(d[1]), int(d[2]), int(d[3])
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.circle(vis, (x + w // 2, y + h // 2), 3, (0, 0, 255), -1)
            max_w = 480
            if vis.shape[1] > max_w:
                k = max_w / vis.shape[1]
                vis = cv2.resize(vis, (max_w, int(vis.shape[0] * k)))
            rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
            with shared.lock:
                shared.preview = rgb

        # ---- fps + tick pacing ----
        frames += 1
        if frames >= 15:
            now = time.perf_counter()
            shared.fps = frames / (now - fps_clock)
            frames = 0
            fps_clock = now

        hz = _clamp(s.tick_hz, 30, 1000)
        budget = 1.0 / hz
        spent = time.perf_counter() - tick_start
        if spent < budget:
            time.sleep(budget - spent)

    ser_mouse.disconnect()
