# pikoc - Pi Pico IIDX controller (JKOC)

CircuitPython firmware for a hand-rewired Konami JKOC (PS2) on a **RP2040 Pico non-W** for **beatoraja**. Keys + turntable -> single HID gamepad.

## Hardware

* Board: RP2040 Pico (non-W)
* `GP0/GP1` - JKOC photointerrupter encoder (quadrature)
* `GP2-GP8` - Keys 1-7 (white/black)
* `GP9` - Start, `GP10` - Select
* Buttons: active-LOW (to GND), internal `Pull.UP` (`code.py:109`)

## Wiring (hand-rewired JKOC -> Pico)

| Function | JKOC wire | Pico | Note `code.py:4` |
|---|---|---|---|
| Key 1 (white) | red | `GP2` | |
| Key 2 (black) | yellow | `GP3` | |
| Key 3 (white) | dark blue | `GP4` | |
| Key 4 (black) | purple | `GP5` | |
| Key 5 (white) | pink | `GP6` | |
| Key 6 (black) | orange | `GP7` | |
| Key 7 (white) | brown | `GP8` | |
| Start | white | `GP9` | |
| Select | light blue | `GP10` | |
| Ground (common) | black + gray | `GND` | both to any `GND`, buttons short to this when pressed |
| VCC | green | **NC** | unused - interrupter powered via `250Ω` to `5V` (see Warning below) |

> **Warning `code.py:4`:** JKOC interrupter is 5V stock. `250Ω` on LED power does **not** protect the phototransistor output - high can be ~5V. RP2040 max is 3.63V (not 5V tolerant). Use divider (`10k/15k` to 3.3V) or power from `3V3` after measuring, not direct 5V to `GP0/GP1`.

## Install

1. Flash CircuitPython for Pico (UF2).
2. Copy `boot.py`, `code.py`, `config.json` to `CIRCUITPY` drive.
3. **Power-cycle** (unplug, not soft reset) after changing `boot.py` - USB descriptor is set at enumeration `boot.py:12`.

## Configuration

`config.json` (live without reflash, `code.py:44`):

```json
{
  "raw_axis_mode": true,
  "axis_scale": 1.0,
  "invert_turntable": false,
  "debounce_ms": 5
}
```

* `raw_axis_mode` `code.py:53` - `true` = `axis_scale` ignored, send `raw_pos &0xFF`.
* `axis_scale` `code.py:57` - `0.1..5.0` scaling of absolute position before `&0xFF` (only when `raw_axis_mode false`). `1.0` = predictable `1` tick `->` `1/255` (`~96` counts/rev, `4x` decode `code.py:79`).
* `invert_turntable` - flip scratch direction.
* `debounce_ms` `0..50` per-button debounce `code.py:69,148` (scratch never debounced `code.py:221`). `5` for JKOC membranes.

## HID

`boot.py:22` single gamepad `Report ID 1`, 3 bytes:

* Byte 0: `X` turntable absolute `0-255` `wrap 255->0` (`0x81 0x02`)
* Byte 1: Keys 1-7 bits 0-6
* Byte 2: Start bit0, Select bit1

`code.py:200` `struct.pack("BBB")`, change-only send at `~1kHz` `code.py:232`.

## beatoraja

* Map `X` axis to Scratch (analog). Threshold is stock `1/50` analog step - leave as-is with `scale 1.0`.
* Map Buttons 1-9 to keys/start/select.

## Repo

```
git log --oneline
5a9de85 revert: remove relative_mode ...
cf047dd fix: per-button debounce ...
747e8cd Initial commit ...
```
