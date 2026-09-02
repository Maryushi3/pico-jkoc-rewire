# pikoc - Pi Pico IIDX controller (JKOC)

CircuitPython firmware for a hand-rewired Konami JKOC (PS2) on a **RP2040 Pico non-W** for **beatoraja**. Keys + turntable -> single HID gamepad with optional digital scratch POV.

## Hardware

* Board: RP2040 Pico (non-W)
* `GP0/GP1` - JKOC photointerrupter encoder (quadrature, 50 Pulses `code.py:112`)
* `GP2-GP8` - Keys 1-7 (white/black)
* `GP9` - Start, `GP10` - Select
* Buttons: active-LOW (to GND), internal `Pull.UP` (`code.py:122`)

## Wiring (hand-rewired JKOC -> Pico)

| Function | JKOC wire | Pico |
|---|---|---|
| Key 1 (white) | red | `GP2` |
| Key 2 (black) | yellow | `GP3` |
| Key 3 (white) | dark blue | `GP4` |
| Key 4 (black) | purple | `GP5` |
| Key 5 (white) | pink | `GP6` |
| Key 6 (black) | orange | `GP7` |
| Key 7 (white) | brown | `GP8` |
| Start | white | `GP9` |
| Select | light blue | `GP10` |
| Ground (common) | black + gray | `GND` |
| VCC | green | **NC** |

> **Warning `code.py:4`:** JKOC interrupter is 5V stock. `250Ω` on LED power does **not** protect the phototransistor output - high can be ~5V. RP2040 max is 3.63V (not 5V tolerant). Use divider (`10k/15k` to 3.3V) or power from `3V3` after measuring, not direct 5V to `GP0/GP1`.

## Install

1. Flash CircuitPython for Pico (UF2).
2. Copy `boot.py`, `code.py`, `config.json` to `CIRCUITPY` drive.
3. **Power-cycle** (unplug, not soft reset) after changing `boot.py` - USB descriptor (`boot.py:33` `4 bytes` with hat) is set at enumeration.

## Configuration

`config.json` (live without reflash, `code.py:36`; `boot.py` hat requires power-cycle):

```json
{
  "raw_axis_mode": true,
  "axis_scale": 1.0,
  "invert_turntable": false,
  "debounce_ms": 5,
  "speedy_math": false,
  "digital_scratch": false,
  "digital_scratch_suppress_analog": false,
  "digital_scratch_timeout_ms": 80
}
```

| Key | Range | Effect `code.py:54` |
|---|---|---|
| `raw_axis_mode` | `bool` | `true` = `axis_scale` ignored, `raw_pos &0xFF` `1 tick=1/255` predictable. |
| `axis_scale` | `0.1..5.0` | Only when `raw false`. `1.0` = `1:1` same as `raw true` unless `speedy_math`. |
| `speedy_math` | `bool` | `false` = classic `raw*scale`. `true` + `raw false` = per-rev `50 Pulses->256` `5.12*scale` with `1 step/ms` smoothing `code.py:122` to hit every `1/255`. |
| `invert_turntable` | `bool` | Flip scratch direction. |
| `debounce_ms` | `0..50` | Per-button debounce `code.py:68,139` (scratch never debounced). `3-5` for old membranes. `0` = bypass. |
| `digital_scratch` | `bool` | `true` = enable POV hat `up`/`down` `code.py:130` (analog still sent in parallel). |
| `digital_scratch_suppress_analog` | `bool` | `true` + `digital true` = hold analog at `127` `code.py:110` for exclusive digital. |
| `digital_scratch_timeout_ms` | `20..500` | Time after last tick before hat returns to neutral `8` `code.py:91` (default `80`). Direction change is immediate. |

Current disk state: `raw false` + `scale 4.0` (high sensitivity test), `speedy` off.

### 1:1 Examples

* **Tick:Tick `1:1` (`1 encoder tick =1 analog step`)** - predictable `&0xFF` `code.py:115`:
  ```json
  { "raw_axis_mode": true, "axis_scale": 1.0, "speedy_math": false, "scratch_smoothing": true }
  ```
  or `raw false` `scale 1.0` `speedy false` same.

* **Rotation:Output `1:1` (`1 full spin =256 steps = wraps to same 0`)** - per-rev correct `50 Pulses ->256` `code.py:117`:
  ```json
  { "raw_axis_mode": false, "axis_scale": 1.0, "speedy_math": true, "scratch_smoothing": false }
  ```
  (`5.12` steps per tick, `50 ticks =256`). Use `scratch_smoothing true` to hit every `1/255` with `1ms` tail, `false` for instant `5` jump no lag.

## HID

`boot.py:33` single gamepad `Report ID 1`, 4 bytes `boot.py:61` `in_report_lengths 4`:

* Byte 0: `X` turntable absolute `0-255` `wrap 255->0` (`0x81 0x02`)
* Byte 1: Keys 1-7 bits 0-6
* Byte 2: Start bit0, Select bit1 (6 pad bits)
* Byte 3: POV hat `4 bits 0=up 4=down 8=neutral` + `4 pad` (`0x09 0x39`)

`code.py:180` `struct.pack("BBBB")` with `BBB` fallback, change-only send at `~1kHz` `code.py:242`.

## beatoraja

* Map `X` axis to Scratch (analog). Threshold is stock `1/50` analog step - leave as-is with `scale 1.0`.
* If `digital_scratch true`, map `POV Up/Down` to scratch up/down for fallback software.
* Map Buttons 1-9 to keys/start/select.

## Credits

* `speedy_math` per-rev `200->256` inspired by [speedypotato/Pico-Game-Controller `pocket-iidx`](https://github.com/speedypotato/Pico-Game-Controller/tree/release/pocket-iidx)
