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

The photointerrupter can stay wired when using the AS5600: it's only read with `"encoder": "optical"`.

### AS5600 magnetic encoder (`"encoder": "magnetic"`, default)

Diametrically magnetized magnet centered over the chip, ~0.5-3 mm air gap.

| breakout pin | Pico | function |
|---|---|---|
| VCC | `3V3(OUT)` (pin 36) | power, **3.3V only** |
| OUT | - | analog/PWM angle output, unused (I2C is read instead) |
| GND | `GND` (e.g. pin 18) | ground |
| DIR | `GND` | direction polarity, must not float; flip direction with `invert_turntable` instead |
| SCL | `GP13` (pin 17) | I2C clock |
| SDA | `GP12` (pin 16) | I2C data |
| GPO | - | programming option pin, leave unconnected |

* never power it from `VBUS`/`VSYS`: the breakout's I2C pull-ups go to VCC and would put 5V on the Pico pins
* most breakouts have SDA/SCL pull-ups; if the serial log says `No pull up found on SDA or SCL`, add 4.7k from each to 3.3V
* the datasheet wants `VDD5V` and `VDD3V3` tied together for 3.3V supply; some breakouts have a jumper for this, check yours if readings are erratic
* boot log prints magnet status and AGC (`0-128` at 3.3V, mid-range is best); too weak/strong magnet is reported
* no automatic fallback: if the chip or magnet isn't detected at boot, the turntable is disabled (buttons still work) and the serial log says why

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
| `encoder` | `string` | `"magnetic"` (AS5600, default) or `"optical"` (photointerrupter, GP0/GP1); explicit, no automatic fallback |
| `as5600_steps_per_rev` | `int` | magnetic only: analog axis steps per platter turn (`16-4096`, default `576` = DAO RED-LMS (2x arcade's `288`, per [DJ-DAO](https://dj-dao.com/en/redlms)), `128` = [iidx_pico](https://github.com/whowechina/iidx_pico) default, `256` = physical 1:1; above ~1000 very fast spins can alias on the 8-bit axis); `raw_axis_mode`, `axis_scale`, `speedy_math` are optical-only |
| `as5600_hysteresis` | `int` | magnetic only: deadband in raw counts (4096/turn) a reversal has to cross, stops sensor noise flickering axis/hat (`0-64`, default `2`, ~0.18°) |
| `raw_axis_mode` | `bool` | when `true` makes 1 physical encoder disc "tick" move the analog axis 1 step (full range is 0-255); mathematical 1:1|
| `axis_scale` | `float` | output axis multiplier; `1.0` = 1:1 same as with raw_axis_mode `true` unless `speedy_math` is `true` |
| `speedy_math` | `bool` | `5.12` scale multiplier to hit full range of the analog axis; with axis_scale `1.0` results in physical 1:1 |
| `invert_turntable` | `bool` | flips scratch direction |
| `debounce_ms` | `int` | button debounce (scratch never debounced); debounces both edges (press and release); `3-5` for old membranes, `0` = bypass |
| `digital_scratch` | `bool` | `true` enables POV hat `up`/`down` (analog still sent in parallel) |
| `digital_scratch_suppress_analog` | `bool` | disables analog output (for digital scratch mapping) |
| `digital_scratch_timeout_ms` | `int` | Time after last tick before hat returns to neutral (default `80`); direction change is immediate |
| `double_tap_window_ms` | `int` | Double/triple tap window for Start/Select `E3`/`E4` (default `300`); `50-1000` |

Current disk state: `encoder magnetic` `576 steps/rev`; optical settings `raw false` + `scale 5` `speedy off` (matches `5` ticks/scroll below).

### 1:1 Examples

* **Magnetic physical `1:1`** (`1 full spin = 256 steps`):
  ```json
  { "encoder": "magnetic", "as5600_steps_per_rev": 256}
  ```

* **Optical Tick:Tick (mathematical) `1:1` (`1 encoder tick = 1 analog step`)** - predictable:
  ```json
  { "encoder": "optical", "raw_axis_mode": true, "axis_scale": 1.0, "speedy_math": false}
  ```
  or `raw false` `scale 1.0` `speedy false` same.

* **Optical Rotation:Output (physical) `1:1` (`1 full spin = 256 steps = wraps to same 0`)** - per-rev correct `50 Pulses ->256`:
  ```json
  { "encoder": "optical", "raw_axis_mode": false, "axis_scale": 1.0, "speedy_math": true}
  ```
  (`5.12` steps per tick, `50 ticks = 256`). May result in difficult song list scrolling, as steps are not identical.


## beatoraja settings

* set analog scratch threshold in Input to 30-40 for default `axis_scale` of 5 to feel okay
* set analog ticks per scroll in Music Select to 5 (match `axis_scale`)
* magnetic at `576` steps/rev moves in 1-step increments instead of optical's 5-step jumps (250/turn); ticks per scroll 5 scrolls ~2.3x as often per turn as before, use 10-12 for about the same; scratch threshold may need retuning
* if mapping for digital scratch, suppress the analog axis in config for mapping
* map buttons and scratch as usual

## todos:

- [ ] LED notifications (WS28xx)
- [ ] additional button hotkeys for more virtual buttons (double/triple Start/Select done)

## Credits

* `speedy_math` inspired by [speedypotato/Pico-Game-Controller `pocket-iidx`](https://github.com/speedypotato/Pico-Game-Controller/tree/release/pocket-iidx)
* Double/triple press `E1-E4` inspired by [CrazyRedMachine/BEMANI_PSX_Adapter](https://github.com/CrazyRedMachine/BEMANI_PSX_Adapter)
* sanity saved by various LLMs
