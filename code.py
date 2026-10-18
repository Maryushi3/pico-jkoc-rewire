"""
code.py - IIDX Controller for JKOC on Pi Pico
"""

import board
import digitalio
import rotaryio
import usb_hid
import struct
import json
import time
import supervisor

# Int ms ticks, wraps at 2**29 (~6.2 days). Float time.monotonic() loses
# precision after ~1h uptime, which breaks ms-level debounce/tap timing.
_ticks_ms = supervisor.ticks_ms
_TICKS_MASK = (1 << 29) - 1  # elapsed = (now - then) & _TICKS_MASK

# -----------------------------------------------
# Load Configuration from File
# -----------------------------------------------

CONFIG = {
    "encoder": "magnetic",
    "as5600_steps_per_rev": 576,
    "as5600_hysteresis": 2,
    "raw_axis_mode": True,
    "axis_scale": 1.0,
    "invert_turntable": False,
    "debounce_ms": 5,
    "speedy_math": False,
    "digital_scratch": False,
    "digital_scratch_suppress_analog": False,
    "digital_scratch_timeout_ms": 80,
    "double_tap_window_ms": 300
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
    if AXIS_SCALE <= 0:
        print(f"axis_scale {AXIS_SCALE} out of range, using 1.0")
        AXIS_SCALE = 1.0
    elif AXIS_SCALE > 5.0:
        print(f"axis_scale {AXIS_SCALE} out of range, clamping to 5.0")
        AXIS_SCALE = 5.0
except Exception:
    AXIS_SCALE = 1.0
INVERT_TURNTABLE = -1 if CONFIG["invert_turntable"] else 1
try:
    _debounce_ms = int(CONFIG["debounce_ms"])
    _debounce_ms = max(0, min(50, _debounce_ms))
except Exception:
    _debounce_ms = 5
DEBOUNCE_MS = _debounce_ms
if DEBOUNCE_MS == 0:
    print("Debounce disabled (0 ms) - membranes may chatter")
else:
    print(f"Debounce: {_debounce_ms} ms")
try:
    SPEEDY_MATH = bool(CONFIG["speedy_math"])
except Exception:
    SPEEDY_MATH = False
print(f"Speedy math (per-rev 50->256 5.12): {SPEEDY_MATH}")
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
DIGITAL_TIMEOUT_MS = _digital_timeout_ms
if DIGITAL_SCRATCH:
    print(f"Digital scratch: POV hat up/down, timeout {_digital_timeout_ms}ms, suppress_analog={DIGITAL_SUPPRESS_ANALOG}")
else:
    print("Digital scratch: disabled (POV neutral)")
# Explicit choice, no automatic fallback: "magnetic" = AS5600, "optical" = JKOC photointerrupter
ENCODER = str(CONFIG["encoder"]).lower()
if ENCODER not in ("magnetic", "optical"):
    print(f'encoder "{ENCODER}" unknown (use "magnetic" or "optical"), using "magnetic"')
    ENCODER = "magnetic"
USE_AS5600 = ENCODER == "magnetic"
try:
    # 576 = DJ-DAO RED-LMS, 2x arcade (288); 8-bit axis wraps every ~0.44 turn
    AS5600_STEPS_PER_REV = int(CONFIG["as5600_steps_per_rev"])
    AS5600_STEPS_PER_REV = max(16, min(4096, AS5600_STEPS_PER_REV))
except Exception:
    AS5600_STEPS_PER_REV = 576
try:
    _as5600_hyst = int(CONFIG["as5600_hysteresis"])
    _as5600_hyst = max(0, min(64, _as5600_hyst))
except Exception:
    _as5600_hyst = 2

# -----------------------------------------------
# AS5600 Magnetic Encoder (I2C, 12-bit = 4096 counts/rev)
# -----------------------------------------------

_AS5600_ADDR = 0x36
_AS5600_REG_CONF = 0x07       # 0x07-0x08, volatile (not burned)
_AS5600_REG_STATUS = 0x0B     # bit5 MD magnet detected, bit4 ML too weak, bit3 MH too strong
_AS5600_REG_RAW_ANGLE = 0x0C  # 0x0C-0x0D, unfiltered by ZPOS/MPOS/hysteresis
_AS5600_REG_AGC = 0x1A
# CONF high byte: SF bits 1:0 (11 = 2x, 0.286ms step response vs 2.2ms default 16x),
# FTH bits 4:2 (000 = slow filter only). Lowest latency, extra noise eaten by hysteresis.
_AS5600_SF = 0b11
_AS5600_FTH = 0b000

_i2c = None
_as5600_ok = False
if USE_AS5600:
    try:
        import busio
        _i2c = busio.I2C(board.GP13, board.GP12, frequency=400000)  # SCL, SDA
        while not _i2c.try_lock():
            pass
        _as_buf1 = bytearray(1)
        _as_buf2 = bytearray(2)
        _i2c.writeto_then_readfrom(_AS5600_ADDR, bytes([_AS5600_REG_STATUS]), _as_buf1)
        _status = _as_buf1[0]
        if not _status & 0x20:
            raise RuntimeError("no magnet detected (STATUS MD=0)")
        _i2c.writeto_then_readfrom(_AS5600_ADDR, bytes([_AS5600_REG_AGC]), _as_buf1)
        print(f"AS5600: magnet ok, AGC={_as_buf1[0]} (mid-range is best; 0-128 at 3.3V)")
        if _status & 0x10:
            print("AS5600: WARNING magnet too weak (move closer)")
        if _status & 0x08:
            print("AS5600: WARNING magnet too strong (move further)")
        _i2c.writeto_then_readfrom(_AS5600_ADDR, bytes([_AS5600_REG_CONF]), _as_buf2)
        _conf_hi = (_as_buf2[0] & 0xE0) | (_AS5600_FTH << 2) | _AS5600_SF
        _i2c.writeto(_AS5600_ADDR, bytes([_AS5600_REG_CONF, _conf_hi, _as_buf2[1]]))
        _i2c.writeto_then_readfrom(_AS5600_ADDR, bytes([_AS5600_REG_RAW_ANGLE]), _as_buf2)
        _as_boot_raw = ((_as_buf2[0] & 0x0F) << 8) | _as_buf2[1]
        _as5600_ok = True
    except Exception as e:
        print("ERROR: AS5600 init failed, turntable DISABLED (buttons still work):", e)
        print('Fix wiring/magnet, or set "encoder": "optical" in config.json for the photointerrupter.')
        if _i2c is not None:
            _i2c.deinit()
            _i2c = None

if _as5600_ok:
    # Position is tracked in output steps (AS5600_STEPS_PER_REV per turn).
    # Sub-step remainder is kept in units of raw_count * steps_per_rev, so one
    # step = 4096 units and the math stays integer. A step only registers once
    # the remainder leaves [-hyst, 4096 + hyst): sensor noise around a step
    # boundary can't flicker the axis/hat back and forth.
    _AS_RAW_REG = bytes([_AS5600_REG_RAW_ANGLE])
    _AS_HYST = _as5600_hyst * AS5600_STEPS_PER_REV
    _AS_UPPER = 4096 + _AS_HYST

    def _as5600_raw():
        _i2c.writeto_then_readfrom(_AS5600_ADDR, _AS_RAW_REG, _as_buf2)
        return ((_as_buf2[0] & 0x0F) << 8) | _as_buf2[1]

    _as_prev_raw = _as_boot_raw
    _as_steps = 0
    _as_frac = 2048  # start mid-step, as far from both boundaries as possible

    def read_tt_position():
        global _as_prev_raw, _as_steps, _as_frac
        try:
            raw = _as5600_raw()
        except OSError:
            # I2C glitch: hold last position
            return _as_steps
        d = (raw - _as_prev_raw) & 0xFFF
        if d == 0:
            return _as_steps
        if d >= 2048:
            # shortest way around the wrap (needs < half turn per poll)
            d -= 4096
        _as_prev_raw = raw
        x = _as_frac + d * AS5600_STEPS_PER_REV
        if x >= _AS_UPPER:
            k = (x - _AS_HYST) >> 12
        elif x < -_AS_HYST:
            k = (x + _AS_HYST) >> 12
        else:
            _as_frac = x
            return _as_steps
        _as_steps += k
        _as_frac = x - (k << 12)
        return _as_steps

    print(f"Encoder: magnetic (AS5600), {AS5600_STEPS_PER_REV} steps/rev, hysteresis {_as5600_hyst} counts")
elif USE_AS5600:
    # Magnetic selected but unusable: hold the axis still rather than silently
    # switching to a sensor that wasn't asked for
    def read_tt_position():
        return 0

    print("Encoder: magnetic (AS5600) FAILED, turntable disabled")
else:
    # rotaryio default divisor=4: 1 count per full quadrature cycle -> JKOC 50 counts/rev.
    _encoder = rotaryio.IncrementalEncoder(board.GP0, board.GP1)

    def read_tt_position():
        return _encoder.position

    print("Encoder: optical (GP0/GP1)")

# -----------------------------------------------
# Turntable Axis
# -----------------------------------------------

# per-rev speedy math: 50 Pulses ->256 steps ->5.12/tick (1:1 physical)
ENC_PULSE = 50
PER_REV_SCALE = 256.0 / ENC_PULSE  # 5.12

_AXIS_SCALE_INT = int(AXIS_SCALE) if AXIS_SCALE == int(AXIS_SCALE) else None
# AS5600 position is already in output steps; raw/scale/speedy are optical-only
_AXIS_DIRECT = RAW_AXIS_MODE or USE_AS5600

def get_axis(pos):
    # Analog suppress: hold center when digital wants exclusive POV
    if DIGITAL_SCRATCH and DIGITAL_SUPPRESS_ANALOG:
        return 127
    raw_pos = pos * INVERT_TURNTABLE

    if _AXIS_DIRECT:
        return raw_pos & 0xFF
    else:
        # Classic raw*scale or per-rev 50->256 when speedy_math
        if SPEEDY_MATH:
            target = raw_pos * PER_REV_SCALE * AXIS_SCALE
        elif _AXIS_SCALE_INT is not None:
            target = raw_pos * _AXIS_SCALE_INT
        else:
            target = raw_pos * AXIS_SCALE
        return int(target) & 0xFF

# Digital scratch POV state (hat 0=up, 4=down, 8=neutral)
_HAT_NEUTRAL = 8
_HAT_UP = 0
_HAT_DOWN = 4
_prev_raw_pov = read_tt_position() * INVERT_TURNTABLE
_last_pov_move = _ticks_ms()
_current_hat = _HAT_NEUTRAL

def get_pov_hat(pos, now):
    global _prev_raw_pov, _last_pov_move, _current_hat
    if not DIGITAL_SCRATCH:
        return _HAT_NEUTRAL
    raw_pos = pos * INVERT_TURNTABLE
    delta = raw_pos - _prev_raw_pov
    if delta != 0:
        # Direction change immediately updates hat
        _current_hat = _HAT_UP if delta > 0 else _HAT_DOWN
        _prev_raw_pov = raw_pos
        _last_pov_move = now
        return _current_hat
    # No movement - check timeout for neutral
    if ((now - _last_pov_move) & _TICKS_MASK) >= DIGITAL_TIMEOUT_MS:
        _current_hat = _HAT_NEUTRAL
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
_last_change = [0] * _NUM_BUTTONS

# Seed initial state from actual pins to avoid false edge on boot
for idx, btn in enumerate(_buttons):
    pressed = not btn.value
    _last_raw[idx] = pressed
    _stable[idx] = pressed
    _last_change[idx] = _ticks_ms()

# Double/triple tap state for Start (E2) / Select (E1) -> E3/E4 (CrazyRed style)
# Only Start/Select are used for hotkeys; keys/TT remain free for settings.
try:
    _double_window_ms = int(CONFIG["double_tap_window_ms"])
    _double_window_ms = max(50, min(1000, _double_window_ms))
except Exception:
    _double_window_ms = 300
_DOUBLE_WINDOW_MS = _double_window_ms
print(f"Double tap window: {_double_window_ms}ms")

class _TapCounter:
    """Counts presses landing within the double tap window of the previous one."""

    def __init__(self, pressed):
        self.prev = pressed
        self.last_press = 0
        self.taps = 0

    def update(self, pressed, now):
        """Return 0 = released, 1 = single, 2 = double, 3 = triple (while held)."""
        elapsed = (now - self.last_press) & _TICKS_MASK
        if pressed and not self.prev:
            # press edge: chain onto previous press if inside window
            if self.taps > 0 and elapsed < _DOUBLE_WINDOW_MS:
                if self.taps < 3:
                    self.taps += 1
            else:
                self.taps = 1
            self.last_press = now
        elif not pressed and self.taps > 0 and elapsed >= _DOUBLE_WINDOW_MS:
            # window expired while released: next press starts fresh
            self.taps = 0
        self.prev = pressed
        if not pressed:
            return 0
        return self.taps if self.taps > 1 else 1

_select_tap = _TapCounter(_stable[8])
_start_tap = _TapCounter(_stable[7])

# extra_byte bits per tap level: bit0=Start/E2, bit1=Select/E1, bit2=E3, bit3=E4
_SELECT_BITS = (0, 0x02, 0x04, 0x06)  # -, E1, E3, E1+E3
_START_BITS = (0, 0x01, 0x08, 0x09)   # -, E2, E4, E2+E4

def read_buttons_debounced(now):
    """Return (key_byte, extra_byte) after per-button debounce + double/triple.
    extra_byte bits: 0=Start/E2, 1=Select/E1, 2=E3, 3=E4
    Single Select -> E1, double -> E3 (no E1), triple -> E1+E3
    Single Start  -> E2, double -> E4 (no E2), triple -> E2+E4
    Turntable is NOT debounced - handled separately for latency.
    If DEBOUNCE_MS==0 this is zero-latency pass-through.
    """
    if DEBOUNCE_MS == 0:
        # Fast path: no timing checks, raw pins straight to key/tap state
        key_byte = 0
        for i in range(7):
            if not _buttons[i].value:
                key_byte |= (1 << i)
        base_start = not _buttons[7].value
        base_select = not _buttons[8].value
    else:
        # Debounced path
        for i, b in enumerate(_buttons):
            raw_pressed = not b.value
            if raw_pressed != _last_raw[i]:
                _last_raw[i] = raw_pressed
                _last_change[i] = now
            # Only promote to stable after signal held for debounce window
            if ((now - _last_change[i]) & _TICKS_MASK) >= DEBOUNCE_MS:
                _stable[i] = _last_raw[i]

        key_byte = 0
        for i in range(7):
            if _stable[i]:
                key_byte |= (1 << i)
        base_start = _stable[7]
        base_select = _stable[8]

    # Only emit when base is held; double/triple are modifiers for that hold
    extra_byte = (_SELECT_BITS[_select_tap.update(base_select, now)]
                  | _START_BITS[_start_tap.update(base_start, now)])

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

def send_report(axis, key_byte, extra_byte, hat=_HAT_NEUTRAL):
    try:
        gamepad.send_report(struct.pack("BBBB", axis, key_byte, extra_byte, hat & 0x0F))
    except OSError:
        # PC not polling
        pass

# -----------------------------------------------
# Main Loop
# -----------------------------------------------

print("IIDX Controller ready.")
print(f"Config: encoder={ENCODER}{'' if _as5600_ok or not USE_AS5600 else ' (FAILED)'} raw_axis={RAW_AXIS_MODE} scale={AXIS_SCALE} invert={INVERT_TURNTABLE==-1} debounce={_debounce_ms}ms hat={'digital' if DIGITAL_SCRATCH else 'off'}")

_prev_axis = -1
_prev_keys = -1
_prev_extra = -1
_prev_hat = -1

# Local binds for main loop hot path
_now_ms = _ticks_ms
_read_tt = read_tt_position
_get_axis = get_axis
_read_buttons = read_buttons_debounced
_get_hat = get_pov_hat
_send = send_report

while True:
    now = _now_ms()

    pos = _read_tt()
    axis = _get_axis(pos)
    key_byte, extra = _read_buttons(now)
    hat = _get_hat(pos, now)

    if axis != _prev_axis or key_byte != _prev_keys or extra != _prev_extra or hat != _prev_hat:
        _send(axis, key_byte, extra, hat)
        _prev_axis = axis
        _prev_keys = key_byte
        _prev_extra = extra
        _prev_hat = hat

    # Throttled poll for closed box no airflow: 0.5ms sleep caps ~2000 loops/s ~60% CPU
    # Keeps <0.7ms latency vs tight busy 0.2ms but stays <55C.
    time.sleep(0.0005)