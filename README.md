# YoloMouse (Python)

Python port of the C++ tool. It captures the screen, detects an object with a
**YOLOv10 `.onnx`** model, and moves the mouse onto it with adjustable
**smoothing**. Same two output backends:

1. **Windows mouse (SendInput)** — pure software, nothing to plug in.
2. **RP2040 / RP2350 USB-HID** — the included Arduino firmware turns the board
   into a real USB mouse; the PC sends it move/click packets over USB-serial.

The GUI (Tkinter) exposes confidence, capture region, target selection,
smoothing/speed, activation key, and a live detection preview.

> The firmware (`firmware/mouse_hid.ino`) and the serial protocol are identical
> to the C++ version, so a board flashed for one works with the other.

---

## 1. Layout

```
YoloMousePy/
├─ main.py                 <- run this
├─ requirements.txt
├─ firmware/mouse_hid.ino  <- flash to the RP2040 / RP2350
└─ yolomouse/
   ├─ config.py            <- Settings + shared state
   ├─ detector.py          <- YOLOv10 ONNX inference
   ├─ capture.py           <- screen capture (mss)
   ├─ backends.py          <- SendInput + serial backends
   ├─ worker.py            <- capture->detect->target->smooth->move loop
   └─ gui.py               <- Tkinter GUI
```

---

## 2. Install Python (do this first)

The `python` that ships as a Microsoft Store alias on Windows often **won't
work** for this (it can fail to import compiled wheels). Install the real thing:

1. Get **Python 3.10–3.12 (64-bit)** from https://www.python.org/downloads/
2. During install, tick **"Add python.exe to PATH"**.
3. Verify in a new terminal:
   ```powershell
   python --version
   ```
   (If it still opens the Store, turn off the alias in
   *Settings → Apps → Advanced app settings → App execution aliases*.)

---

## 3. Install dependencies

```powershell
cd YoloMousePy
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` installs the **CPU** ONNX Runtime by default. For GPU,
install one of these *instead* of `onnxruntime`:

```powershell
pip uninstall onnxruntime
pip install onnxruntime-directml      # any GPU (AMD/NVIDIA/Intel) on Windows
# or
pip install onnxruntime-gpu           # NVIDIA CUDA (needs CUDA + cuDNN)
```

The app auto-selects DirectML/CUDA if present and falls back to CPU.

---

## 4. Get a YOLOv10 `.onnx` model

```bash
pip install ultralytics
# pretrained nano, or swap in your own best.pt
yolo export model=yolov10n.pt format=onnx opset=13
```

For "find the dot on a black screen", train a single-class model on images of
the dot and export `best.pt` the same way. The app expects YOLOv10's
end-to-end output `[1, N, 6]` (`x1,y1,x2,y2,score,class`) — the default export.

---

## 5. Flash the firmware (only for the RP2040 / RP2350 backend)

1. Install the **Arduino IDE**.
2. *File → Preferences → Additional Boards Manager URLs*:
   `https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json`
   then *Boards Manager* → install **"Raspberry Pi Pico/RP2040/RP2350"**.
3. *Manage Libraries* → install **Adafruit TinyUSB Library**.
4. Pick your board (*Raspberry Pi Pico* or *Pico 2* for RP2350).
5. **Important:** *Tools → USB Stack → "Adafruit TinyUSB"**.
6. Open `firmware/mouse_hid.ino`, hold BOOTSEL while first plugging in, Upload.

The board then appears as both a COM port **and** a USB mouse.

---

## 6. Run it

```powershell
python main.py
```

1. **Model:** *Browse* to your `.onnx`, tick *Use GPU* if installed, *Load model*.
2. **Output backend:** *Windows mouse* (ready), or *RP2040/RP2350 HID* → pick the
   COM port → *Connect* ("verified" = firmware answered the ping).
3. **Activation:** turn on **MOVER ENABLED**, pick a mode:
   *Hold key* (default: hold **Right Mouse**), *Toggle key*, or *Always on*.
4. **Smoothing & movement:** tune to taste.
5. Aim at a screen with the target (e.g. a white dot on black). The preview
   shows green detection boxes; the cursor eases onto the chosen target.

### Smoothing controls
| Control | Effect |
|---|---|
| **Smoothing** | 0 = snap instantly; higher = slower, smoother glide |
| **Max speed (px/tick)** | hard cap on cursor movement per tick |
| **Gain** | overall strength multiplier |
| **Deadzone (px)** | stop (and optionally click) once this close |
| **Target jitter filter** | smooths the *target point* to kill detection jitter |
| **Tick rate (Hz)** | how often the loop runs |

---

## 7. Troubleshooting

- **Nothing moves:** confirm *MOVER ENABLED* is on, you're holding the trigger
  key, and the preview shows a detection (lower *Confidence* if not).
- **Serial "open (unverified)":** port opened but no firmware reply — re-check
  USB Stack = Adafruit TinyUSB and that the sketch is running.
- **`onnxruntime` import error / DLL load failed:** you're likely on the Store
  Python — install python.org Python (section 2) and reinstall deps.
- **No preview:** `pip install Pillow`.
- **`.onyx` vs `.onnx`:** the format is `.onnx`; rename if needed.
- Multi-monitor capture uses the **primary** monitor.
