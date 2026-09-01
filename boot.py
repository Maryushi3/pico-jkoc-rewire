"""
boot.py  -  IIDX Controller HID descriptor & USB Naming
Runs once on power-up before code.py.
"""

import usb_hid
import supervisor

# ------------------------------------------------------------------
# Set Custom USB Product & Manufacturer Names
# ------------------------------------------------------------------
supervisor.set_usb_identification(
    manufacturer="Custom",
    product="IIDX JKOC Controller"
)

# ------------------------------------------------------------------
# Decide HID mode from config.json (power-cycle required after change)
# false = absolute 0-255 (beatoraja default, wraps 255->0)
# true  = relative -127..127 delta (test mode for fallback software)
# ------------------------------------------------------------------
try:
    import json as _json

    _cfg = {}
    with open("/config.json", "r") as _f:
        _cfg = _json.load(_f)
    RELATIVE_MODE = bool(_cfg.get("relative_mode", False))
except Exception as _e:
    # Boot filesystem may not be ready or file missing -> default absolute
    print("boot.py: could not load relative_mode, defaulting to absolute:", _e)
    RELATIVE_MODE = False

print("boot.py: turntable mode:", "relative delta" if RELATIVE_MODE else "absolute")

# ------------------------------------------------------------------
# HID Report Descriptor (3 bytes, Report ID 1)
# ------------------------------------------------------------------
if RELATIVE_MODE:
    # Signed delta: host sees -127..127, Relative. Wrap-free velocity.
    _AXIS_LOG_MIN = bytes([0x15, 0x81])  # Logical Minimum (-127)
    _AXIS_LOG_MAX = bytes([0x25, 0x7F])  # Logical Maximum (127)
    _AXIS_INPUT = 0x06  # Relative
else:
    # Unsigned absolute: host sees 0..255, Absolute. Beatoraja diffs frames.
    _AXIS_LOG_MIN = bytes([0x15, 0x00])          # Logical Minimum (0)
    _AXIS_LOG_MAX = bytes([0x26, 0xFF, 0x00])    # Logical Maximum (255)
    _AXIS_INPUT = 0x02  # Absolute

IIDX_REPORT_DESCRIPTOR = (
    bytes([
        0x05, 0x01,        # Usage Page (Generic Desktop)
        0x09, 0x05,        # Usage (Gamepad)
        0xA1, 0x01,        # Collection (Application)
        0x85, 0x01,        #   Report ID 1
    ])
    + bytes([0x09, 0x30]) + _AXIS_LOG_MIN + _AXIS_LOG_MAX + bytes([
        0x75, 0x08,        #   Report Size (8 bits)
        0x95, 0x01,        #   Report Count (1)
        0x81, _AXIS_INPUT,  #   Input (Data, Variable, Absolute/Relative)
    ])
    + bytes([
        # -- 7 key buttons (bits 0-6) --------------------------------
        0x05, 0x09,        #   Usage Page (Button)
        0x19, 0x01,        #   Usage Minimum (Button 1)
        0x29, 0x07,        #   Usage Maximum (Button 7)
        0x15, 0x00,        #   Logical Minimum (0)
        0x25, 0x01,        #   Logical Maximum (1)
        0x75, 0x01,        #   Report Size (1)
        0x95, 0x07,        #   Report Count (7)
        0x81, 0x02,        #   Input (Data, Variable, Absolute)

        # -- 1 padding bit (byte-align after 7 buttons) --------------
        0x75, 0x01,        #   Report Size (1)
        0x95, 0x01,        #   Report Count (1)
        0x81, 0x03,        #   Input (Constant)

        # -- Start + Select (bits 0-1) --------------------------------
        0x05, 0x09,        #   Usage Page (Button)
        0x19, 0x08,        #   Usage Minimum (Button 8)
        0x29, 0x09,        #   Usage Maximum (Button 9)
        0x15, 0x00,        #   Logical Minimum (0)
        0x25, 0x01,        #   Logical Maximum (1)
        0x75, 0x01,        #   Report Size (1)
        0x95, 0x02,        #   Report Count (2)
        0x81, 0x02,        #   Input (Data, Variable, Absolute)

        # -- 6 padding bits (byte-align) ------------------------------
        0x75, 0x01,
        0x95, 0x06,
        0x81, 0x03,

        0xC0,              # End Collection
    ])
)

iidx_gamepad = usb_hid.Device(
    report_descriptor=IIDX_REPORT_DESCRIPTOR,
    usage_page=0x01,          # Generic Desktop
    usage=0x05,               # Gamepad
    report_ids=(1,),
    in_report_lengths=(3,),   # 1 byte axis + 1 byte keys + 1 byte start/sel
    out_report_lengths=(0,),
)

usb_hid.enable((iidx_gamepad,))