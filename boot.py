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
# HID Report Descriptor (3 bytes, Report ID 1)
# Absolute 0-255 (beatoraja diffs frames, wraps 255->0)
# ------------------------------------------------------------------
IIDX_REPORT_DESCRIPTOR = bytes([
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x05,        # Usage (Gamepad)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID 1

    # -- Turntable axis (uint8, 0-255, absolute) ----------------
    0x09, 0x30,        #   Usage (X)
    0x15, 0x00,        #   Logical Minimum (0)
    0x26, 0xFF, 0x00,  #   Logical Maximum (255)
    0x75, 0x08,        #   Report Size (8 bits)
    0x95, 0x01,        #   Report Count (1)
    0x81, 0x02,        #   Input (Data, Variable, Absolute)

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

iidx_gamepad = usb_hid.Device(
    report_descriptor=IIDX_REPORT_DESCRIPTOR,
    usage_page=0x01,          # Generic Desktop
    usage=0x05,               # Gamepad
    report_ids=(1,),
    in_report_lengths=(3,),   # 1 byte axis + 1 byte keys + 1 byte start/sel
    out_report_lengths=(0,),
)

usb_hid.enable((iidx_gamepad,))
