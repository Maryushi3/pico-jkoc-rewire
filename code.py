"""
code.py  -  IIDX Controller (Optimized with Config & Latency Protection)

Hardware:
  GP0  - Encoder channel A  (JKOC photointerrupter)
  GP1  - Encoder channel B  (JKOC photointerrupter)
  GP2  - Key 1  (white)
  GP3  - Key 2  (black)
  GP4  - Key 3  (white)
  GP5  - Key 4  (black)
  GP6  - Key 5  (white)
  GP7  - Key 6  (black)
  GP8  - Key 7  (white)
  GP9  - Start
  GP10 - Select
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
    "debounce_ms": 0
}

try:
    with open("/config.json", "r") as f:
        user_config = json.load(f)
        CONFIG.update(user_config)
        print("Successfully loaded config.json")
except Exception as e:
    print("Could not load config.json, using defaults:", e)

RAW_AXIS_MODE = CONFIG["raw_axis_mode"]
AXIS_SCALE = CONFIG["axis_scale"]
INVERT_TURNTABLE = -1 if CONFIG["invert_turntable"] else 1
DEBOUNCE_SEC = CONFIG["debounce_ms"] / 1000.0

# -----------------------------------------------
# Encoder Setup
# -----------------------------------------------

_encoder = rotaryio.IncrementalEncoder(board.GP0, board.GP1)

def get_axis():
    raw_pos = _encoder.position * INVERT_TURNTABLE
    
    if RAW_AXIS_MODE:
        # Zero precision loss, instant 8-bit wrap
        return raw_pos & 0xFF
    else:
        # Scaled sensitivity mode
        return int(raw_pos * AXIS_SCALE) & 0xFF

# -----------------------------------------------
# Buttons Setup
# -----------------------------------------------

_BUTTON_PINS = (
    board.GP2, board.GP3, board.GP4, board.GP5, 
    board.GP6, board.GP7, board.GP8, board.GP9, board.GP10
)

_buttons = []
for _pin in _BUTTON_PINS:
    _b = digitalio.DigitalInOut(_pin)
    _b.direction = digitalio.Direction.INPUT
    _b.pull = digitalio.Pull.UP  # active-LOW
    _buttons.append(_b)

_keys = _buttons[:7]
_start_pin = _buttons[7]
_select_pin = _buttons[8]

def read_buttons():
    key_byte = 0
    for i, b in enumerate(_keys):
        if not b.value:
            key_byte |= (1 << i)

    extra_byte = 0
    if not _start_pin.value:
        extra_byte |= 0x01
    if not _select_pin.value:
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

_prev_axis = -1
_prev_keys = -1
_prev_extra = -1
_last_change_time = 0

while True:
    current_time = time.monotonic()
    
    axis = get_axis()
    key_byte, extra = read_buttons()

    if axis != _prev_axis or key_byte != _prev_keys or extra != _prev_extra:
        # Optional software debouncing
        if (current_time - _last_change_time) >= DEBOUNCE_SEC:
            send_report(axis, key_byte, extra)
            _prev_axis = axis
            _prev_keys = key_byte
            _prev_extra = extra
            _last_change_time = current_time