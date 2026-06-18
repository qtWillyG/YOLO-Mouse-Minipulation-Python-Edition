"""Two interchangeable cursor backends.

  WindowsMouseBackend - standard Windows mouse events via SendInput (ctypes)
  SerialMouseBackend  - sends packets to the RP2040/RP2350 HID firmware

Wire protocol (matches firmware/mouse_hid.ino), fixed 7-byte packets:
  [0xAA][cmd][d0][d1][d2][d3][checksum]
  checksum = cmd ^ d0 ^ d1 ^ d2 ^ d3
  'M' move : d0,d1 = int16 dx LE ; d2,d3 = int16 dy LE
  'B' button: d0 = button(0=L,1=R,2=M) ; d1 = state(1 down,0 up)
  'C' click : d0 = button
  'P' ping  : firmware replies 'K'
"""
import ctypes
from ctypes import wintypes

# ---------------------------------------------------------------------------
# Windows SendInput backend
# ---------------------------------------------------------------------------
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

_ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


_SendInput = ctypes.windll.user32.SendInput

_BTN_DOWN = (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_MIDDLEDOWN)
_BTN_UP = (MOUSEEVENTF_LEFTUP, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_MIDDLEUP)


def _send(flags, dx=0, dy=0):
    inp = _INPUT(type=0)
    inp.mi = _MOUSEINPUT(dx, dy, 0, flags, 0, None)
    _SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


class WindowsMouseBackend:
    name = "Windows SendInput"

    def ok(self):
        return True

    def move_relative(self, dx, dy):
        dx, dy = int(dx), int(dy)
        if dx or dy:
            _send(MOUSEEVENTF_MOVE, dx, dy)

    def set_button(self, button, down):
        flags = _BTN_DOWN[button] if down else _BTN_UP[button]
        _send(flags)

    def click(self, button):
        self.set_button(button, True)
        self.set_button(button, False)


# ---------------------------------------------------------------------------
# RP2040 / RP2350 serial backend
# ---------------------------------------------------------------------------
def _clamp16(v):
    return max(-32768, min(32767, int(v)))


def _packet(cmd, d0=0, d1=0, d2=0, d3=0):
    chk = cmd ^ d0 ^ d1 ^ d2 ^ d3
    return bytes([0xAA, cmd, d0, d1, d2, d3, chk])


class SerialMouseBackend:
    name = "RP2040/RP2350 HID"

    def __init__(self):
        self.ser = None
        self.verified = False

    def connect(self, port):
        import serial  # pyserial
        try:
            self.ser = serial.Serial(port, 115200, timeout=0.05, write_timeout=0.2)
        except Exception:
            self.ser = None
            self.verified = False
            return False
        # ping -> expect 'K'
        self.verified = False
        try:
            self.ser.reset_input_buffer()
            self.ser.write(_packet(ord('P')))
            reply = self.ser.read(1)
            self.verified = (reply == b'K')
        except Exception:
            pass
        return True

    def disconnect(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.verified = False

    def ok(self):
        return self.ser is not None and self.ser.is_open

    def move_relative(self, dx, dy):
        if not self.ok():
            return
        dx, dy = int(dx), int(dy)
        if not (dx or dy):
            return
        x = _clamp16(dx) & 0xFFFF
        y = _clamp16(dy) & 0xFFFF
        try:
            self.ser.write(_packet(ord('M'), x & 0xFF, (x >> 8) & 0xFF,
                                   y & 0xFF, (y >> 8) & 0xFF))
        except Exception:
            pass

    def set_button(self, button, down):
        if self.ok():
            try:
                self.ser.write(_packet(ord('B'), button, 1 if down else 0))
            except Exception:
                pass

    def click(self, button):
        if self.ok():
            try:
                self.ser.write(_packet(ord('C'), button))
            except Exception:
                pass

    @staticmethod
    def list_ports():
        try:
            from serial.tools import list_ports
            return [p.device for p in list_ports.comports()]
        except Exception:
            return []
