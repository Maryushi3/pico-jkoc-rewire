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
    "debounce_ms": 5,
    "speedy_math": False,
    "scratch_smoothing": True,
    "digital_scratch": False,
    "digital_scratch_suppress_analog": False,
    "digital_scratch_timeout_ms": 80
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
try:
    SPEEDY_MATH = bool(CONFIG["speedy_math"])
except Exception:
    SPEEDY_MATH = False
print(f"Speedy math (per-rev 200->256): {SPEEDY_MATH}")
try:
    SCRATCH_SMOOTHING = bool(CONFIG["scratch_smoothing"])
except Exception:
    SCRATCH_SMOOTHING = True
print(f"Scratch smoothing (1 step/ms): {SCRATCH_SMOOTHING}")
try:
    DIGITAL_SCRATCH = bool(CONFIG["digital_scratch"])
except Exception:
    DIGITAL_SCRATCH = False
try:
    DIGITAL_SUPPRESS_ANALOG = bool(CONFIG["digital_scratch_suppress_analog"])
except Exception:
    DIGITAL_SUPPRESS_ANALOG = False
try:
    _digital_timeout_ms = int(CONFIG["digital_scratch_timeout_ms"])
    _digital_timeout_ms = max(20, min(500, _digital_timeout_ms))
except Exception:
    _digital_timeout_ms = 80
DIGITAL_TIMEOUT_SEC = _digital_timeout_ms / 1000.0
if DIGITAL_SCRATCH:
    print(f"Digital scratch: POV hat up/down, timeout {_digital_timeout_ms}ms, suppress_analog={DIGITAL_SUPPRESS_ANALOG}")
else:
    print("Digital scratch: disabled (POV neutral)")

# -----------------------------------------------
# Encoder Setup
# -----------------------------------------------

# rotaryio does 4x decoding. JKOC is 50 Pulses per rev (50 holes).
# pocket-iidx uses 24 PPR ->96 Pulses. No divisor arg on RP2040 build.
_encoder = rotaryio.IncrementalEncoder(board.GP0, board.GP1)

# per-rev speedy math: 50 Pulses per rev ->256 steps ->5.12/tick (1:1 physical)
ENC_PULSE = 50
PER_REV_SCALE = 256.0 / ENC_PULSE  # 5.12

# Smoothing state for scaled mode only (raw_axis_mode false)
# When speedy_math true -> per-rev correct cur/200*256 with smoothing; else raw*scale 1:1
if not RAW_AXIS_MODE:
    if SPEEDY_MATH:
        _disp_init_scale = PER_REV_SCALE * AXIS_SCALE
    elif SCRATCH_SMOOTHING:
        _disp_init_scale = AXIS_SCALE
    else:
        _disp_init_scale = AXIS_SCALE
else:
    _disp_init_scale = 1.0
_disp_pos = float(_encoder.position * INVERT_TURNTABLE * _disp_init_scale)

_AXIS_SCALE_INT = int(AXIS_SCALE) if AXIS_SCALE == int(AXIS_SCALE) else None

def get_axis(now=None):
    global _disp_pos
    # Analog suppress: hold center when digital mode wants exclusive POV
    if DIGITAL_SCRATCH and DIGITAL_SUPPRESS_ANALOG:
        return 127
    # Local bind for speed (avoids global lookup in hot loop)
    enc = _encoder
    inv = INVERT_TURNTABLE
    raw_pos = enc.position * inv

    if RAW_AXIS_MODE:
        # Zero precision loss, instant 8-bit wrap - no smoothing, int only
        return raw_pos & 0xFF
    else:
        # Use int when scale is integer to avoid float
        if SPEEDY_MATH:
            # per-rev 50->256: keep float for 5.12
            target = raw_pos * PER_REV_SCALE * AXIS_SCALE
        elif _AXIS_SCALE_INT is not None:
            target = raw_pos * _AXIS_SCALE_INT
        else:
            target = raw_pos * AXIS_SCALE
        if not SCRATCH_SMOOTHING:
            # No smoothing - instant jump, keep disp in sync for next smooth enable
            _disp_pos = float(target)
            return int(target) & 0xFF
        # Smoothing: 1 step/ms to hit every 1/255 when scale>1
        diff = target - _disp_pos
        # abs(diff) micro-opt: manual
        if diff < 0:
            diff_neg = -diff
            if diff_neg < 0.5:
                _disp_pos = target
            elif diff < -1.0:
                _disp_pos -= 1.0
            else:
                _disp_pos = target
        else:
            if diff < 0.5:
                _disp_pos = target
            elif diff > 1.0:
                _disp_pos += 1.0
            else:
                _disp_pos = target

        return int(_disp_pos) & 0xFF

# Digital scratch POV state (hat 0=up, 4=down, 8=neutral)
_HAT_NEUTRAL = 8
_HAT_UP = 0
_HAT_DOWN = 4
_prev_raw_pov = _encoder.position * INVERT_TURNTABLE
_last_pov_move = time.monotonic()
_current_hat = _HAT_NEUTRAL

def get_pov_hat(now):
    global _prev_raw_pov, _last_pov_move, _current_hat
    if not DIGITAL_SCRATCH:
        return _HAT_NEUTRAL
    raw_pos = _encoder.position * INVERT_TURNTABLE
    delta = raw_pos - _prev_raw_pov
    if delta != 0:
        # Direction change immediately updates hat
        _current_hat = _HAT_UP if delta > 0 else _HAT_DOWN
        _prev_raw_pov = raw_pos
        _last_pov_move = now
        return _current_hat
    # No movement - check timeout for neutral
    if (now - _last_pov_move) >= DIGITAL_TIMEOUT_SEC:
        if _current_hat != _HAT_NEUTRAL:
            _current_hat = _HAT_NEUTRAL
        return _HAT_NEUTRAL
    return _current_hat

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

_report_struct = struct.Struct("BBBB")
def send_report(axis, key_byte, extra_byte, hat=_HAT_NEUTRAL):
    # Direct 4-byte report (boot.py 4), no fallback needed - saves try/except on hot path
    try:
        gamepad.send_report(_report_struct.pack(axis, key_byte, extra_byte, hat & 0x0F))
    except OSError:
        # PC not polling
        pass

# -----------------------------------------------
# Main Loop
# -----------------------------------------------

print("IIDX Controller ready.")
print(f"Config: raw_axis={RAW_AXIS_MODE} scale={AXIS_SCALE} invert={INVERT_TURNTABLE==-1} debounce={_debounce_ms}ms hat={'digital' if DIGITAL_SCRATCH else 'off'}")

_prev_axis = -1
_prev_keys = -1
_prev_extra = -1
_prev_hat = -1

# Local binds for main loop hot path
_monotonic = time.monotonic
_get_axis = get_axis
_read_buttons = read_buttons_debounced
_get_hat = get_pov_hat
_send = send_report

while True:
    now = _monotonic()

    axis = _get_axis(now)
    key_byte, extra = _read_buttons(now)
    hat = _get_hat(now)

    if axis != _prev_axis or key_byte != _prev_keys or extra != _prev_extra or hat != _prev_hat:
        _send(axis, key_byte, extra, hat)
        _prev_axis = axis
        _prev_keys = key_byte
        _prev_extra = extra
        _prev_hat = hat

    # Throttled poll for closed box no airflow: 0.5ms sleep caps ~2000 loops/s ~60% CPU
    # Keeps <0.7ms latency vs tight busy 0.2ms but stays <55C.
    time.sleep(0.0005)