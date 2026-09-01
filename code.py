"""
code.py  -  IIDX Controller (Optimized with Config & Latency Protection)

Hardware (RP2040 Pico non-W, CircuitPython):
  GP0  - Encoder channel A  (JKOC photointerrupter) - WARNING: 3.3V only, no 5V
  GP1  - Encoder channel B  (JKOC photointerrupter) - see note below
  GP2  - Key 1  (white)
  GP3  - Key 2  (black)
  GP4  - Key 3  (white)
  GP5  - Key 4  (black)
  GP6  - Key 5  (white)
  GP7  - Key 6  (black)
  GP8  - Key 7  (white)
  GP9  - Start
  GP10 - Select

JKOC photointerrupter is 5V stock. Power via 250 Ohm from 5V limits LED
current but collector output can still swing to ~5V. RP2040 GPIO abs max
is 3.63V and not 5V tolerant. Feed collector via divider (e.g. 10k/15k to
3.3V) or power the sensor from 3V3 if you measured clean switching.
Direct 5V -> GP0/GP1 will eventually damage the Pico.
"""

import board
import digitalio
import rotaryio
import usb_hid
import struct
import json
import time

# -----------------------------------------------
# Load Configuration from File
# -----------------------------------------------

CONFIG = {
    "raw_axis_mode": True,
    "axis_scale": 1.0,
    "invert_turntable": False,
    "debounce_ms": 5
}

try:
    with open("/config.json", "r") as f:
        user_config = json.load(f)
        CONFIG.update(user_config)
        print("Successfully loaded config.json")
except Exception as e:
    print("Could not load config.json, using defaults:", e)

# Validate / clamp config (prevents nonsense from typos)
try:
    RAW_AXIS_MODE = bool(CONFIG["raw_axis_mode"])
except Exception:
    RAW_AXIS_MODE = True
try:
    AXIS_SCALE = float(CONFIG["axis_scale"])
    if AXIS_SCALE <= 0 or AXIS_SCALE > 5.0:
        print(f"axis_scale {AXIS_SCALE} out of range, clamping to 1.0")
        AXIS_SCALE = 1.0
except Exception:
    AXIS_SCALE = 1.0
INVERT_TURNTABLE = -1 if CONFIG["invert_turntable"] else 1
try:
    _debounce_ms = int(CONFIG["debounce_ms"])
    _debounce_ms = max(0, min(50, _debounce_ms))
except Exception:
    _debounce_ms = 5
DEBOUNCE_SEC = _debounce_ms / 1000.0
if DEBOUNCE_SEC == 0:
    print("Debounce disabled (0 ms) - membranes may chatter")
else:
    print(f"Debounce: {_debounce_ms} ms")

# -----------------------------------------------
# Encoder Setup
# -----------------------------------------------

# rotaryio does 4x decoding. JKOC 24 PPR -> ~96 counts/rev.
# No divisor arg on RP2040 build - counts are raw quadrature edges.
_encoder = rotaryio.IncrementalEncoder(board.GP0, board.GP1)

def get_axis():
    raw_pos = _encoder.position * INVERT_TURNTABLE

    if RAW_AXIS_MODE:
        # Zero precision loss, instant 8-bit wrap.
        # This is ABSOLUTE 0-255: beatoraja diffs successive reads.
        # e.g. 10 -> 15 means +5 steps, 255 -> 2 means +3 (wrap).
        return raw_pos & 0xFF
    else:
        # Scaled sensitivity mode - multiplies absolute before wrap.
        # <1.0 = less sensitive, >1.0 = more sensitive.
        return int(raw_pos * AXIS_SCALE) & 0xFF

# -----------------------------------------------
# Buttons Setup + Per-Button Debounce
# -----------------------------------------------

_BUTTON_PINS = (
    board.GP2, board.GP3, board.GP4, board.GP5,
    board.GP6, board.GP7, board.GP8, board.GP9, board.GP10
)

_buttons = []
for _pin in _BUTTON_PINS:
    _b = digitalio.DigitalInOut(_pin)
    _b.direction = digitalio.Direction.INPUT
    _b.pull = digitalio.Pull.UP  # active-LOW: pressed = GND
    _buttons.append(_b)

_NUM_BUTTONS = len(_buttons)

# Per-button debounce state: raw vs stable (pressed=True)
_last_raw = [False] * _NUM_BUTTONS
_stable = [False] * _NUM_BUTTONS
_last_change = [0.0] * _NUM_BUTTONS

# Seed initial state from actual pins to avoid false edge on boot
for idx, btn in enumerate(_buttons):
    pressed = not btn.value
    _last_raw[idx] = pressed
    _stable[idx] = pressed
    _last_change[idx] = time.monotonic()

def read_buttons_debounced(now):
    """Return (key_byte, extra_byte) after per-button debounce.
    Turntable is NOT debounced - handled separately for latency.
    If DEBOUNCE_SEC==0 this is zero-latency pass-through.
    """
    if DEBOUNCE_SEC == 0:
        # Fast path: no timing checks
        key_byte = 0
        for i in range(7):
            if not _buttons[i].value:
                key_byte |= (1 << i)
        extra_byte = 0
        if not _buttons[7].value:
            extra_byte |= 0x01
        if not _buttons[8].value:
            extra_byte |= 0x02
        return key_byte, extra_byte

    # Debounced path
    for i, b in enumerate(_buttons):
        raw_pressed = not b.value
        if raw_pressed != _last_raw[i]:
            _last_raw[i] = raw_pressed
            _last_change[i] = now
        # Only promote to stable after signal held for debounce window
        if (now - _last_change[i]) >= DEBOUNCE_SEC:
            _stable[i] = _last_raw[i]

    key_byte = 0
    for i in range(7):
        if _stable[i]:
            key_byte |= (1 << i)
    extra_byte = 0
    if _stable[7]:
        extra_byte |= 0x01
    if _stable[8]:
        extra_byte |= 0x02
    return key_byte, extra_byte

# -----------------------------------------------
# HID Device Setup
# -----------------------------------------------

gamepad = None
for device in usb_hid.devices:
    if device.usage == 0x05 and device.usage_page == 0x01:
        gamepad = device
        break

if gamepad is None:
    raise RuntimeError("IIDX HID gamepad not found - check boot.py and fully power cycle.")

def send_report(axis, key_byte, extra_byte):
    try:
        gamepad.send_report(struct.pack("BBB", axis, key_byte, extra_byte))
    except OSError:
        # Prevents code crash if PC stops polling USB
        pass

# -----------------------------------------------
# Main Loop
# -----------------------------------------------

print("IIDX Controller ready.")
print(f"Config: raw_axis={RAW_AXIS_MODE} scale={AXIS_SCALE} invert={INVERT_TURNTABLE==-1} debounce={_debounce_ms}ms")

_prev_axis = -1
_prev_keys = -1
_prev_extra = -1

while True:
    now = time.monotonic()

    # Axis is never debounced - scratch needs every edge
    axis = get_axis()
    key_byte, extra = read_buttons_debounced(now)

    if axis != _prev_axis or key_byte != _prev_keys or extra != _prev_extra:
        send_report(axis, key_byte, extra)
        _prev_axis = axis
        _prev_keys = key_byte
        _prev_extra = extra

    # ~1000 Hz poll: keeps USB <1ms latency but avoids 100% busy loop
    # and lets CircuitPython supervisor run. Increase to 0.002 if hot.
    time.sleep(0.001)