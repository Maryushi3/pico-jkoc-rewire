# Pico JKOC rewire

CircuitPython firmware for a **rewired** JKOC (Konami IIDX official controller). Designed for **Raspberry Pi Pico** (or any other RP2040 board). Tested with **beatoraja**. Keys + turntable -> single HID gamepad with optional digital scratch POV. Configurable via a json file.

Why CircuitPython and not just speedy's code or something else? I wanted to quickly test just the encoder and have something immediately easily readable. It then spiralled into full controller code, because what's wrong with adding some buttons, right? With code so simple, Python overhead doesn't impact the performance and is easy to modify and iterate on. That's exactly what I needed.

## Wiring (hand-rewired JKOC -> Pico)

I just let the Pi Pico hang around along the edge of the case under the turntable.

### Photointerrupter encoder PCB (pins labeled on PCB)

| PCB pin | Pico | function |
|---|---|---|
| 1 | `GP0` or `GP1` | detector A |
| 2 | `3.3V` via 250 Ohm resistor | LED power |
| 3 | `GND` | ground |
| 4 | `GP1` or `GP0` | detector B |
| 5 | `3.3V` via 250 Ohm resistor | LED power |

You can short PCB pins 2 and 5 and connect them via a single 250 Ohm resistor to Pico's 3.3V.

### Buttons PCB connector

| JKOC wire | Pico | function |
|---|---|---|
| red | `GP2` | key 1 (white) |
| yellow | `GP3` | key 2 (black) |
| dark blue | `GP4` | key 3 (white) |
| purple | `GP5` | key 4 (black) |
| pink | `GP6` | key 5 (white) |
| orange | `GP7` | key 6 (black) |
| brown | `GP8` | key 7 (white) |
| white | `GP9` | start |
| light blue | `GP10` | select |
| black | `GND` | common ground |
| gray | `GND` | common ground |
| green | - | VCC |

The green cable is connected to VCC line on the factory controller PCB, but is left not connected anywhere on the button PCB. You can isolate it and leave it not connected.

## Install

1. flash CircuitPython for Pico UF2
2. copy `boot.py`, `code.py`, `config.json` to `CIRCUITPY` drive
3. adjust config.json to taste (but defaults are sane)
3. **power-cycle** (unplug, not soft reset)

## Configuration

| entry | type | effect |
|---|---|---|
| `raw_axis_mode` | `bool` | when `true` makes 1 physical encoder disc "tick" move the analog axis 1 step (full range is 0-255); mathematical 1:1|
| `axis_scale` | `float` | output axis multiplier; `1.0` = 1:1 same as with raw_axis_mode `true` unless `speedy_math` is `true` |
| `speedy_math` | `bool` | `5.12` scale multiplier to hit full range of the analog axis; with axis_scale `1.0` results in physical 1:1 |
| `invert_turntable` | `bool` | flips scratch direction |
| `debounce_ms` | `int` | button debounce (scratch never debounced); debounces both edges (press and release); `3-5` for old membranes, `0` = bypass |
| `digital_scratch` | `bool` | `true` enables POV hat `up`/`down` (analog still sent in parallel) |
| `digital_scratch_suppress_analog` | `bool` | disables analog output (for digital scratch mapping) |
| `digital_scratch_timeout_ms` | `int` | Time after last tick before hat returns to neutral (default `80`); direction change is immediate |

Current disk state: `raw false` + `scale 5` `speedy off` (matches `5` ticks/scroll below).

### 1:1 Examples

* **Tick:Tick (mathematical) `1:1` (`1 encoder tick = 1 analog step`)** - predictable:
  ```json
  { "raw_axis_mode": true, "axis_scale": 1.0, "speedy_math": false}
  ```
  or `raw false` `scale 1.0` `speedy false` same.

* **Rotation:Output (physical) `1:1` (`1 full spin = 256 steps = wraps to same 0`)** - per-rev correct `50 Pulses ->256` `code.py:117`:
  ```json
  { "raw_axis_mode": false, "axis_scale": 1.0, "speedy_math": true}
  ```
  (`5.12` steps per tick, `50 ticks = 256`). May result in difficult song list scrolling, as steps are not identical.


## beatoraja settings

* set analog scratch threshold in Input to 30-40 for default `axis_scale` of 5 to feel okay
* set analog ticks per scroll in Music Select to 5 (match `axis_scale`)
* if mapping for digital scratch, suppress the analog axis in config for mapping
* map buttons and scratch as usual

## todos:

- [ ] key-selectable modes on bootup
- [ ] LED notifications (WS28xx)
- [ ] additional button hotkeys for more virtual buttons

## Credits

* `speedy_math` inspired by [speedypotato/Pico-Game-Controller `pocket-iidx`](https://github.com/speedypotato/Pico-Game-Controller/tree/release/pocket-iidx)
* sanity saved by various LLMs
