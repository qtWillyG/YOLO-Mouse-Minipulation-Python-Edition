"""Shared settings + cross-thread state for YoloMouse (Python)."""
from dataclasses import dataclass, replace
import threading


@dataclass
class Settings:
    # output backend: "windows" (SendInput) or "serial" (RP2040/RP2350 HID)
    backend: str = "windows"

    # detection
    conf: float = 0.35
    use_gpu: bool = True          # try DirectML/CUDA provider, else CPU

    # capture
    full_screen: bool = True      # whole primary monitor, or...
    fov_size: int = 640           # ...a centered square of this many px

    # targeting
    target_mode: str = "cursor"   # "cursor" | "center" | "score"
    target_ema: float = 0.40      # 0..0.95 jitter filter on the target point

    # smoothing / movement
    smoothing: float = 0.70       # 0 = snap, ->1 = very smooth/slow
    max_speed: float = 60.0       # max cursor px moved per tick
    deadzone: float = 3.0         # stop within this many px
    gain: float = 1.0             # overall strength multiplier

    # activation
    activation: str = "hold"      # "hold" | "toggle" | "always"
    activation_vk: int = 0x02     # VK_RBUTTON (hold right mouse button)
    click_on_target: bool = False

    # loop
    tick_hz: int = 144


class Shared:
    """Everything the GUI thread and worker thread exchange."""
    def __init__(self):
        self.lock = threading.Lock()
        self.settings = Settings()

        # commands: GUI -> worker
        self.model_path = None
        self.do_load = False
        self.port = None
        self.do_connect = False
        self.do_disconnect = False

        # status: worker -> GUI
        self.running = True
        self.mover_enabled = False
        self.model_loaded = False
        self.serial_connected = False
        self.serial_verified = False
        self.active = False
        self.fps = 0.0
        self.det_count = 0
        self.status = "Idle. Load a model to begin."
        self.provider = "-"

        # preview (RGB numpy array, already downscaled), guarded by lock
        self.preview = None
        self.preview_enabled = True

    def snapshot_settings(self) -> Settings:
        with self.lock:
            return replace(self.settings)
