"""Tkinter GUI: smoothing sliders, backend/model/activation controls, preview."""
import tkinter as tk
from tkinter import ttk, filedialog

from .backends import SerialMouseBackend

try:
    from PIL import Image, ImageTk
    _HAVE_PIL = True
except Exception:
    _HAVE_PIL = False


_KEYS = [
    ("Right Mouse", 0x02), ("Mouse 4 (XBUTTON1)", 0x05), ("Mouse 5 (XBUTTON2)", 0x06),
    ("Left Mouse", 0x01), ("Left Shift", 0xA0), ("Left Ctrl", 0xA2), ("Left Alt", 0xA4),
    ("Caps Lock", 0x14), ("Space", 0x20), ("F1", 0x70), ("F2", 0x71), ("F3", 0x72),
]
_KEY_NAMES = [k[0] for k in _KEYS]
_VK_BY_NAME = {k[0]: k[1] for k in _KEYS}
_NAME_BY_VK = {k[1]: k[0] for k in _KEYS}

_ACT = {"Hold key": "hold", "Toggle key": "toggle", "Always on": "always"}
_ACT_REV = {v: k for k, v in _ACT.items()}
_TGT = {"Nearest to cursor": "cursor", "Nearest to screen center": "center",
        "Highest score": "score"}
_TGT_REV = {v: k for k, v in _TGT.items()}


def _scrollable(parent):
    canvas = tk.Canvas(parent, highlightthickness=0, bg="#202024")
    sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg="#202024")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
    return inner


class App:
    def __init__(self, root, shared):
        self.root = root
        self.shared = shared
        root.title("YoloMouse (Python) - YOLOv10 cursor mover")
        root.geometry("560x920")
        root.configure(bg="#202024")

        f = _scrollable(root)
        s = shared.settings

        # ---- model ----
        box = self._frame(f, "Model")
        self.model_var = tk.StringVar()
        tk.Entry(box, textvariable=self.model_var).pack(fill="x", padx=6)
        row = tk.Frame(box, bg="#202024"); row.pack(fill="x", padx=6, pady=3)
        tk.Button(row, text="Browse", command=self._browse).pack(side="left")
        tk.Button(row, text="Load model", command=self._load).pack(side="left", padx=4)
        self.use_gpu = tk.BooleanVar(value=s.use_gpu)
        tk.Checkbutton(row, text="Use GPU (DirectML/CUDA)", variable=self.use_gpu,
                       bg="#202024", fg="white", selectcolor="#404048").pack(side="left")
        self.model_lbl = tk.Label(box, text="not loaded", bg="#202024", fg="#ffaa66")
        self.model_lbl.pack(anchor="w", padx=6)

        # ---- output backend ----
        box = self._frame(f, "Output backend")
        self.backend = tk.StringVar(value=s.backend)
        tk.Radiobutton(box, text="Windows mouse (SendInput)", variable=self.backend,
                       value="windows", bg="#202024", fg="white",
                       selectcolor="#404048").pack(anchor="w", padx=6)
        tk.Radiobutton(box, text="RP2040/RP2350 HID (serial)", variable=self.backend,
                       value="serial", bg="#202024", fg="white",
                       selectcolor="#404048").pack(anchor="w", padx=6)
        row = tk.Frame(box, bg="#202024"); row.pack(fill="x", padx=6, pady=3)
        self.port = ttk.Combobox(row, values=SerialMouseBackend.list_ports(), width=12)
        self.port.pack(side="left")
        tk.Button(row, text="Refresh", command=self._refresh_ports).pack(side="left", padx=3)
        tk.Button(row, text="Connect", command=self._connect).pack(side="left")
        tk.Button(row, text="Disconnect", command=self._disconnect).pack(side="left", padx=3)
        self.serial_lbl = tk.Label(box, text="disconnected", bg="#202024", fg="#ffaa66")
        self.serial_lbl.pack(anchor="w", padx=6)

        # ---- activation ----
        box = self._frame(f, "Activation")
        self.mover_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(box, text="MOVER ENABLED (master switch)",
                       variable=self.mover_enabled, bg="#202024", fg="#88ff88",
                       selectcolor="#404048").pack(anchor="w", padx=6)
        row = tk.Frame(box, bg="#202024"); row.pack(fill="x", padx=6, pady=2)
        tk.Label(row, text="Mode", bg="#202024", fg="white").pack(side="left")
        self.act_mode = ttk.Combobox(row, values=list(_ACT.keys()), width=12, state="readonly")
        self.act_mode.set(_ACT_REV[s.activation]); self.act_mode.pack(side="left", padx=4)
        tk.Label(row, text="Key", bg="#202024", fg="white").pack(side="left")
        self.act_key = ttk.Combobox(row, values=_KEY_NAMES, width=18, state="readonly")
        self.act_key.set(_NAME_BY_VK.get(s.activation_vk, "Right Mouse"))
        self.act_key.pack(side="left", padx=4)
        self.click_on_target = tk.BooleanVar(value=s.click_on_target)
        tk.Checkbutton(box, text="Click left button when on target",
                       variable=self.click_on_target, bg="#202024", fg="white",
                       selectcolor="#404048").pack(anchor="w", padx=6)

        # ---- detection & capture ----
        box = self._frame(f, "Detection & capture")
        self.conf = self._slider(box, "Confidence", 0.05, 0.95, 0.01, s.conf)
        self.full_screen = tk.BooleanVar(value=s.full_screen)
        tk.Checkbutton(box, text="Capture full screen", variable=self.full_screen,
                       bg="#202024", fg="white", selectcolor="#404048").pack(anchor="w", padx=6)
        self.fov = self._slider(box, "FOV box size (px)", 128, 1080, 1, s.fov_size)
        row = tk.Frame(box, bg="#202024"); row.pack(fill="x", padx=6, pady=2)
        tk.Label(row, text="Target", bg="#202024", fg="white").pack(side="left")
        self.target_mode = ttk.Combobox(row, values=list(_TGT.keys()), width=24, state="readonly")
        self.target_mode.set(_TGT_REV[s.target_mode]); self.target_mode.pack(side="left", padx=4)

        # ---- smoothing & movement ----
        box = self._frame(f, "Smoothing & movement")
        self.smoothing = self._slider(box, "Smoothing (0 snap .. high smooth)", 0.0, 0.99, 0.01, s.smoothing)
        self.max_speed = self._slider(box, "Max speed (px/tick)", 1, 300, 1, s.max_speed)
        self.gain = self._slider(box, "Gain", 0.1, 3.0, 0.05, s.gain)
        self.deadzone = self._slider(box, "Deadzone (px)", 0, 30, 1, s.deadzone)
        self.target_ema = self._slider(box, "Target jitter filter", 0.0, 0.95, 0.01, s.target_ema)
        self.tick_hz = self._slider(box, "Tick rate (Hz)", 30, 500, 1, s.tick_hz)

        # ---- status & preview ----
        box = self._frame(f, "Status")
        self.status_lbl = tk.Label(box, text="", bg="#202024", fg="white",
                                   justify="left", wraplength=500, anchor="w")
        self.status_lbl.pack(fill="x", padx=6)
        self.stat2 = tk.Label(box, text="", bg="#202024", fg="#aad4ff", anchor="w")
        self.stat2.pack(fill="x", padx=6)
        self.preview_enabled = tk.BooleanVar(value=True)
        tk.Checkbutton(box, text="Show preview" + ("" if _HAVE_PIL else "  (pip install Pillow)"),
                       variable=self.preview_enabled, bg="#202024", fg="white",
                       selectcolor="#404048").pack(anchor="w", padx=6)
        self.preview_lbl = tk.Label(box, bg="#101012")
        self.preview_lbl.pack(padx=6, pady=4)
        self._photo = None

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick()

    # ---- small builders ----
    def _frame(self, parent, title):
        lf = tk.LabelFrame(parent, text=title, bg="#202024", fg="#cfcfd6",
                           padx=2, pady=4)
        lf.pack(fill="x", padx=8, pady=5)
        return lf

    def _slider(self, parent, label, lo, hi, res, init):
        var = tk.DoubleVar(value=init)
        tk.Scale(parent, label=label, from_=lo, to=hi, resolution=res,
                 orient="horizontal", variable=var, length=500,
                 bg="#202024", fg="white", troughcolor="#404048",
                 highlightthickness=0).pack(fill="x", padx=6)
        return var

    # ---- button handlers ----
    def _browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("ONNX model", "*.onnx"), ("All files", "*.*")])
        if p:
            self.model_var.set(p)

    def _load(self):
        self.shared.model_path = self.model_var.get().strip()
        if self.shared.model_path:
            self.shared.do_load = True

    def _refresh_ports(self):
        self.port["values"] = SerialMouseBackend.list_ports()

    def _connect(self):
        p = self.port.get().strip()
        if p:
            self.shared.port = p
            self.shared.do_connect = True

    def _disconnect(self):
        self.shared.do_disconnect = True

    # ---- periodic sync + status ----
    def _tick(self):
        sh = self.shared
        if not sh.running:          # stop rescheduling once we're closing
            return
        with sh.lock:
            st = sh.settings
            st.backend = self.backend.get()
            st.conf = float(self.conf.get())
            st.use_gpu = bool(self.use_gpu.get())
            st.full_screen = bool(self.full_screen.get())
            st.fov_size = int(self.fov.get())
            st.target_mode = _TGT[self.target_mode.get()]
            st.target_ema = float(self.target_ema.get())
            st.smoothing = float(self.smoothing.get())
            st.max_speed = float(self.max_speed.get())
            st.deadzone = float(self.deadzone.get())
            st.gain = float(self.gain.get())
            st.activation = _ACT[self.act_mode.get()]
            st.activation_vk = _VK_BY_NAME[self.act_key.get()]
            st.click_on_target = bool(self.click_on_target.get())
            st.tick_hz = int(self.tick_hz.get())
        sh.mover_enabled = bool(self.mover_enabled.get())
        sh.preview_enabled = bool(self.preview_enabled.get())

        # status labels
        if sh.model_loaded:
            self.model_lbl.config(text=f"loaded ({sh.provider})", fg="#88ff88")
        else:
            self.model_lbl.config(text="not loaded", fg="#ffaa66")
        if sh.serial_verified:
            self.serial_lbl.config(text="verified", fg="#88ff88")
        elif sh.serial_connected:
            self.serial_lbl.config(text="open (unverified)", fg="#ffff66")
        else:
            self.serial_lbl.config(text="disconnected", fg="#ffaa66")
        self.status_lbl.config(text=sh.status)
        self.stat2.config(text=f"FPS: {sh.fps:.0f}   Detections: {sh.det_count}   "
                               f"Mover active: {'YES' if sh.active else 'no'}")

        # preview
        if _HAVE_PIL and self.preview_enabled.get():
            with sh.lock:
                frame = sh.preview
            if frame is not None:
                img = Image.fromarray(frame)
                self._photo = ImageTk.PhotoImage(img)
                self.preview_lbl.config(image=self._photo)

        self.root.after(40, self._tick)

    def _on_close(self):
        self.shared.running = False
        self.root.after(120, self.root.destroy)
