"""A look-alike of gpiozero for the browser (the real one needs threads and pins).

It supports the parts PiPath's activities use: LED, PWMLED, RGBLED, LEDBoard, LEDBarGraph,
Buzzer, TonalBuzzer, Servo, Button, MotionSensor, DigitalInputDevice and DistanceSensor, with
their usual methods (on, off, toggle, blink, pulse, beep, value, color, wait_for_press,
when_pressed, when_in_range ...). Errors have gpiozero's names, so the Coach explains them
the same way. install() puts it where `import gpiozero` finds it.
"""
from __future__ import annotations

import inspect
import math
import re
import sys
import types

from . import core


# ---------------------------------------------------------------- errors (same names as gpiozero's)

class GPIOZeroError(Exception):
    pass


class DeviceClosed(GPIOZeroError):
    pass


class GPIODeviceError(GPIOZeroError):
    pass


class GPIODeviceClosed(GPIODeviceError, DeviceClosed):
    pass


class GPIOPinInUse(GPIODeviceError):
    pass


class PinError(GPIOZeroError):
    pass


class PinInvalidPin(PinError, ValueError):
    pass


class PinPWMUnsupported(PinError, AttributeError):
    pass


class BadEventHandler(GPIOZeroError, ValueError):
    pass


class OutputDeviceError(GPIOZeroError):
    pass


class OutputDeviceBadValue(OutputDeviceError, ValueError):
    pass


class InputDeviceError(GPIOZeroError):
    pass


class BadPinFactory(GPIOZeroError, ImportError):
    pass


# ---------------------------------------------------------------- helpers

def _pin_number(pin) -> int:
    if isinstance(pin, bool):
        raise PinInvalidPin(f"{pin!r} is not a valid pin name")
    if isinstance(pin, int):
        n = pin
    elif isinstance(pin, str) and (m := re.fullmatch(r"(?:GPIO|BCM)?\s*(\d+)", pin.strip(), re.I)):
        n = int(m.group(1))
    else:
        raise PinInvalidPin(f"{pin!r} is not a valid pin name")
    if not 0 <= n <= 27:
        raise PinInvalidPin(f"{pin!r} is not a valid pin name")
    return n


def _check_handler(value):
    if value is None:
        return None
    if not callable(value):
        raise BadEventHandler("value must be None or a callable")
    try:
        sig = inspect.signature(value)
        required = [p for p in sig.parameters.values()
                    if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty]
        if len(required) > 1:
            raise BadEventHandler("value must accept zero or one argument")
        takes = len(sig.parameters) > 0 and any(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
                                                for p in sig.parameters.values())
    except (TypeError, ValueError):
        takes = False
    return value, takes


def _fire(handler, device):
    if handler is None:
        return
    fn, takes = handler
    fn(device) if takes else fn()


# ---------------------------------------------------------------- devices

class Device:
    def __init__(self):
        self._closed = False
        core.devices.append(self)

    @property
    def closed(self):
        return self._closed

    def close(self):
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _board_info(self):
        return None


class Pin:
    """What `button.pin` is: it knows its GPIO number (button.pin.number), like gpiozero's pin objects."""

    def __init__(self, number: int):
        self.number = number
        self.info = types.SimpleNamespace(name=f"GPIO{number}", names={f"GPIO{number}", str(number)})

    def __str__(self):
        return f"GPIO{self.number}"

    __repr__ = __str__

    def __eq__(self, other):
        return isinstance(other, Pin) and other.number == self.number or other == self.number

    def __hash__(self):
        return hash(self.number)


class GPIODevice(Device):
    def __init__(self, pin=None):
        if pin is None:
            raise GPIODeviceError("No pin given")
        n = _pin_number(pin)
        owner = core.pin_owner.get(n)
        if owner is not None and not owner.closed:
            raise GPIOPinInUse(f"pin GPIO{n} is already in use by {owner!r}")
        super().__init__()
        self._pin = n
        core.pin_owner[n] = self

    @property
    def pin(self):
        return Pin(self._pin)

    def close(self):
        if not self._closed:
            super().close()
            if core.pin_owner.get(self._pin) is self:
                del core.pin_owner[self._pin]

    def _check_open(self):
        if self._closed:
            raise GPIODeviceClosed(f"{type(self).__name__} is closed or uninitialized")

    def __repr__(self):
        if self._closed:
            return f"<gpiozero.{type(self).__name__} object closed>"
        return f"<gpiozero.{type(self).__name__} object on pin GPIO{self._pin}, is_active={bool(self.is_active)}>"

    @property
    def is_active(self):
        return bool(self.value)


# -------- outputs

class _Blinker:
    """A background blink, pulse or beep for one output device."""

    def __init__(self, dev, on_time, off_time, fade_in, fade_out, n):
        self.dev, self.on_time, self.off_time = dev, on_time, off_time
        self.fade_in, self.fade_out, self.n = fade_in, fade_out, n
        self.done = False
        self.handle = None
        self.stage = "on"
        self.count = 0
        self.fade_step = 0

    def start(self):
        self._begin_on()

    def stop(self):
        self.done = True
        core.cancel(self.handle)

    # one cycle: fade in -> on -> fade out -> off
    def _begin_on(self):
        if self.n is not None and self.count >= self.n:
            self.done = True
            return
        self.count += 1
        if self.fade_in > 0:
            self.stage, self.fade_step = "fade_in", 0
            self._fade()
        else:
            self._set(1.0)
            self.stage = "on"
            self.handle = core.call_later(self.on_time, self._begin_out)

    def _begin_out(self):
        if self.fade_out > 0:
            self.stage, self.fade_step = "fade_out", 0
            self._fade()
        else:
            self._set(0.0)
            self.stage = "off"
            self.handle = core.call_later(self.off_time, self._begin_on)

    FADE_STEPS = 25

    def _fade(self):
        total = self.fade_in if self.stage == "fade_in" else self.fade_out
        self.fade_step += 1
        frac = self.fade_step / self.FADE_STEPS
        self._set(frac if self.stage == "fade_in" else 1.0 - frac)
        if self.fade_step >= self.FADE_STEPS:
            if self.stage == "fade_in":
                self.stage = "on"
                self.handle = core.call_later(self.on_time, self._begin_out)
            else:
                self.stage = "off"
                self.handle = core.call_later(self.off_time, self._begin_on)
        else:
            self.handle = core.call_later(total / self.FADE_STEPS, self._fade)

    def _set(self, v):
        self.dev._set_raw(v)


class OutputDevice(GPIODevice):
    def __init__(self, pin=None, active_high=True, initial_value=False):
        super().__init__(pin)
        self.active_high = active_high
        self._blinker = None
        self._value = 0.0
        if initial_value is not None:
            self._value = float(bool(initial_value)) if not isinstance(initial_value, float) else float(initial_value)

    # logical value (1 = lit/on), regardless of active_high
    def _set_raw(self, v):
        self._value = float(v)

    def _stop_blink(self):
        if self._blinker is not None:
            self._blinker.stop()
            self._blinker = None

    @property
    def value(self):
        self._check_open()
        return self._value if self._is_pwm else int(self._value >= 0.5)

    _is_pwm = False

    @value.setter
    def value(self, v):
        self._check_open()
        self._stop_blink()
        self._write(v)

    def _write(self, v):
        if isinstance(v, bool):
            v = float(v)
        if not isinstance(v, (int, float)):
            raise OutputDeviceBadValue("Value must be a number")
        if self._is_pwm:
            if not 0 <= v <= 1:
                raise OutputDeviceBadValue("PWM value must be between 0 and 1")
            self._set_raw(v)
        else:
            self._set_raw(1.0 if v else 0.0)

    def on(self):
        self._check_open()
        self._stop_blink()
        self._set_raw(1.0)

    def off(self):
        self._check_open()
        self._stop_blink()
        self._set_raw(0.0)

    def toggle(self):
        self._check_open()
        self._stop_blink()
        self._set_raw(0.0 if self._value >= 0.5 else 1.0)

    @property
    def is_active(self):
        return self._value > 0

    @property
    def is_lit(self):
        return self.is_active

    def _background(self, on_time, off_time, fade_in, fade_out, n, background):
        self._check_open()
        self._stop_blink()
        b = _Blinker(self, on_time, off_time, fade_in, fade_out, n)
        self._blinker = b
        b.start()
        if not background:
            if n is None:
                core.pause()                      # a never-ending blink: waits for Stop, like gpiozero
            core.wait_until(lambda: b.done or self._blinker is not b)
            if self._blinker is b:
                self._blinker = None

    def blink(self, on_time=1, off_time=1, n=None, background=True):
        self._background(on_time, off_time, 0, 0, n, background)

    def close(self):
        if not self._closed:
            self._stop_blink()
            self._value = 0.0
        super().close()

    def _board_info(self):
        return type(self).__name__, [self._pin], {self._pin: round(self._value, 2)}


class DigitalOutputDevice(OutputDevice):
    pass


class LED(DigitalOutputDevice):
    pass


class Buzzer(DigitalOutputDevice):
    def beep(self, on_time=1, off_time=1, n=None, background=True):
        self.blink(on_time, off_time, n, background)


class PWMOutputDevice(OutputDevice):
    _is_pwm = True

    def __init__(self, pin=None, active_high=True, initial_value=0, frequency=100):
        super().__init__(pin, active_high, initial_value)
        self.frequency = frequency

    def blink(self, on_time=1, off_time=1, fade_in_time=0, fade_out_time=0, n=None, background=True):
        self._background(on_time, off_time, fade_in_time, fade_out_time, n, background)

    def pulse(self, fade_in_time=1, fade_out_time=1, n=None, background=True):
        self._background(0, 0, fade_in_time, fade_out_time, n, background)


class PWMLED(PWMOutputDevice):
    pass


# -------- groups of LEDs

class _GroupMixin:
    """Shared by RGBLED / LEDBoard / LEDBarGraph: they are made of lights that each own a pin."""

    def _stop_group_blink(self):
        b = getattr(self, "_gblinker", None)
        if b is not None:
            b.stop()
            self._gblinker = None


class _GroupBlinker(_Blinker):
    def _set(self, v):
        self.dev._set_all(v)


class LEDCollection(_GroupMixin, Device):
    def __init__(self, *children):
        super().__init__()
        self._leds = list(children)
        self._gblinker = None

    def __len__(self):
        return len(self._leds)

    def __getitem__(self, i):
        return self._leds[i]

    def __iter__(self):
        return iter(self._leds)

    @property
    def leds(self):
        return tuple(self._leds)

    def _set_all(self, v):
        for led in self._leds:
            led._write(v if led._is_pwm else (1.0 if v >= 0.5 else 0.0))

    def close(self):
        if not self._closed:
            self._stop_group_blink()
            for led in self._leds:
                led.close()
        super().close()

    def _blink_all(self, on_time, off_time, fade_in, fade_out, n, background):
        self._stop_group_blink()
        for led in self._leds:
            led._stop_blink()
        b = _GroupBlinker(self, on_time, off_time, fade_in, fade_out, n)
        self._gblinker = b
        b.start()
        if not background:
            if n is None:
                core.pause()
            core.wait_until(lambda: b.done or self._gblinker is not b)

    def on(self):
        self._stop_group_blink()
        for led in self._leds:
            led.on()

    def off(self):
        self._stop_group_blink()
        for led in self._leds:
            led.off()

    def toggle(self):
        self._stop_group_blink()
        for led in self._leds:
            led.toggle()

    def blink(self, on_time=1, off_time=1, *args, **kw):
        if self._leds and self._leds[0]._is_pwm:
            fade_in = kw.pop("fade_in_time", args[0] if len(args) > 0 else 0)
            fade_out = kw.pop("fade_out_time", args[1] if len(args) > 1 else 0)
            n = kw.pop("n", args[2] if len(args) > 2 else None)
            bg = kw.pop("background", args[3] if len(args) > 3 else True)
        else:
            fade_in = fade_out = 0
            n = kw.pop("n", args[0] if len(args) > 0 else None)
            bg = kw.pop("background", args[1] if len(args) > 1 else True)
        self._blink_all(on_time, off_time, fade_in, fade_out, n, bg)

    def pulse(self, fade_in_time=1, fade_out_time=1, n=None, background=True):
        self._blink_all(0, 0, fade_in_time, fade_out_time, n, background)

    @property
    def is_lit(self):
        return any(led.is_lit for led in self._leds)

    @property
    def value(self):
        return tuple(led.value for led in self._leds)

    @value.setter
    def value(self, vals):
        self._stop_group_blink()
        vals = tuple(vals)
        if len(vals) != len(self._leds):
            raise OutputDeviceBadValue("value must be a tuple with one entry per LED")
        for led, v in zip(self._leds, vals):
            led.value = v


class LEDBoard(LEDCollection):
    def __init__(self, *pins, pwm=False, active_high=True, initial_value=False, **named):
        cls = PWMLED if pwm else LED
        children, self._named = [], {}
        made = []
        try:
            for p in pins:
                made.append(cls(p, active_high=active_high, initial_value=initial_value))
            for name, p in named.items():
                led = cls(p, active_high=active_high, initial_value=initial_value)
                made.append(led)
                self._named[name] = led
        except Exception:
            for m in made:
                m.close()
            raise
        children = made
        super().__init__(*children)

    def __getattr__(self, name):
        named = self.__dict__.get("_named", {})
        if name in named:
            return named[name]
        raise AttributeError(name)


class LEDBarGraph(LEDCollection):
    def __init__(self, *pins, pwm=False, active_high=True, initial_value=0):
        cls = PWMLED if pwm else LED
        made = []
        try:
            for p in pins:
                made.append(cls(p, active_high=active_high))
        except Exception:
            for m in made:
                m.close()
            raise
        super().__init__(*made)
        self._pwm = pwm
        self.value = initial_value

    @property
    def value(self):
        n = len(self._leds)
        if not n:
            return 0
        lit = sum(led.value for led in self._leds)
        return lit / n

    @value.setter
    def value(self, v):
        self._stop_group_blink()
        if not isinstance(v, (int, float)) or not -1 <= v <= 1:
            raise OutputDeviceBadValue("LEDBarGraph value must be between -1 and 1")
        n = len(self._leds)
        leds = self._leds if v >= 0 else list(reversed(self._leds))
        count = abs(v) * n
        for i, led in enumerate(leds):
            if self._pwm:
                led.value = min(1.0, max(0.0, count - i))
            else:
                led.value = 1 if count - i >= 0.5 - 1e-9 and (count - i) > 0 else 0

    @property
    def lit_count(self):
        return sum(1 for led in self._leds if led.is_lit)

    @lit_count.setter
    def lit_count(self, n):
        self.value = n / len(self._leds) if self._leds else 0


class RGBLED(_GroupMixin, Device):
    def __init__(self, red=None, green=None, blue=None, active_high=True, initial_value=(0, 0, 0), pwm=True):
        cls = PWMLED if pwm else LED
        made = []
        try:
            for p in (red, green, blue):
                made.append(cls(p, active_high=active_high))
        except Exception:
            for m in made:
                m.close()
            raise
        super().__init__()
        self._leds = made
        self._pwm = pwm
        self._gblinker = None
        self.color = initial_value

    @property
    def red(self):
        return self._leds[0].value

    @red.setter
    def red(self, v):
        self._stop_group_blink()
        self._leds[0].value = v

    @property
    def green(self):
        return self._leds[1].value

    @green.setter
    def green(self, v):
        self._stop_group_blink()
        self._leds[1].value = v

    @property
    def blue(self):
        return self._leds[2].value

    @blue.setter
    def blue(self, v):
        self._stop_group_blink()
        self._leds[2].value = v

    @property
    def color(self):
        return tuple(led.value for led in self._leds)

    @color.setter
    def color(self, rgb):
        self._stop_group_blink()
        try:
            r, g, b = rgb
        except (TypeError, ValueError):
            raise OutputDeviceBadValue("color must be a tuple of three numbers (red, green, blue)") from None
        for led, v in zip(self._leds, (r, g, b)):
            led.value = v

    value = color

    @property
    def is_lit(self):
        return any(led.is_lit for led in self._leds)

    def on(self):
        self.color = (1, 1, 1)

    def off(self):
        self.color = (0, 0, 0)

    def toggle(self):
        self.color = (0, 0, 0) if self.is_lit else (1, 1, 1)

    def _set_all(self, v):
        for led in self._leds:
            led._write(v)

    def blink(self, on_time=1, off_time=1, fade_in_time=0, fade_out_time=0, on_color=(1, 1, 1), off_color=(0, 0, 0), n=None, background=True):
        self._stop_group_blink()
        for led in self._leds:
            led._stop_blink()
        dev = self

        class _B(_Blinker):
            def _set(self, v):
                dev.color = tuple(o + (c - o) * v for c, o in zip(on_color, off_color))
                dev._gblinker = self

        b = _B(self, on_time, off_time, fade_in_time, fade_out_time, n)
        self._gblinker = b
        b.start()
        if not background:
            if n is None:
                core.pause()
            core.wait_until(lambda: b.done or self._gblinker is not b)

    def pulse(self, fade_in_time=1, fade_out_time=1, on_color=(1, 1, 1), off_color=(0, 0, 0), n=None, background=True):
        self.blink(0, 0, fade_in_time, fade_out_time, on_color, off_color, n, background)

    def close(self):
        if not self._closed:
            self._stop_group_blink()
            for led in self._leds:
                led.close()
        super().close()

    def _board_info(self):
        pins = [led._pin for led in self._leds]
        return "RGBLED", pins, {}          # the three lights report their own pins; the board groups them


# -------- servo and tonal buzzer

class Servo(GPIODevice):
    def __init__(self, pin=None, initial_value=0, min_pulse_width=1 / 1000, max_pulse_width=2 / 1000, frame_width=20 / 1000):
        super().__init__(pin)
        self._value = None
        if initial_value is not None:
            self.value = initial_value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._check_open()
        if v is not None and not -1 <= float(v) <= 1:
            raise OutputDeviceBadValue("Servo value must be between -1 and 1, or None")
        self._value = None if v is None else float(v)

    def min(self):
        self.value = -1

    def mid(self):
        self.value = 0

    def max(self):
        self.value = 1

    def detach(self):
        self._value = None

    @property
    def is_active(self):
        return self._value is not None

    def _board_info(self):
        return "Servo", [self._pin], {self._pin: self._value if self._value is not None else 0.0}


class Tone(float):
    """A musical note: Tone("A4"), Tone(midi=69) or Tone(440)."""
    _NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

    def __new__(cls, value=None, *, frequency=None, midi=None, note=None):
        if value is not None:
            if isinstance(value, str):
                note = value
            elif isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 127 and frequency is None:
                midi = value
            else:
                frequency = float(value)
        if note is not None:
            m = re.fullmatch(r"([A-Ga-g])([#b♯♭]?)(-?\d+)", str(note))
            if not m:
                raise ValueError(f"Invalid note specification: {note!r}")
            n = cls._NOTES[m.group(1).upper()] + {"#": 1, "♯": 1, "b": -1, "♭": -1, "": 0}[m.group(2)]
            midi = n + (int(m.group(3)) + 1) * 12
        if midi is not None:
            frequency = 440.0 * 2 ** ((midi - 69) / 12)
        if frequency is None:
            raise ValueError("Tone needs a note, a MIDI number or a frequency")
        return super().__new__(cls, frequency)

    @property
    def frequency(self):
        return float(self)

    @property
    def midi(self):
        return int(round(69 + 12 * math.log2(float(self) / 440.0)))

    @property
    def note(self):
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        m = self.midi
        return f"{names[m % 12]}{m // 12 - 1}"


class TonalBuzzer(GPIODevice):
    def __init__(self, pin=None, initial_value=None, mid_tone=Tone("A4"), octaves=1):
        super().__init__(pin)
        self.mid_tone = Tone(mid_tone)
        self.octaves = octaves
        self._tone = None
        if initial_value is not None:
            self.value = initial_value

    @property
    def tone(self):
        return self._tone

    @property
    def value(self):
        if self._tone is None:
            return None
        return max(-1.0, min(1.0, math.log2(float(self._tone) / float(self.mid_tone)) / self.octaves))

    @value.setter
    def value(self, v):
        self._tone = None if v is None else Tone(frequency=float(self.mid_tone) * 2 ** (float(v) * self.octaves))

    @property
    def min_tone(self):
        return Tone(frequency=float(self.mid_tone) * 2 ** -self.octaves)

    @property
    def max_tone(self):
        return Tone(frequency=float(self.mid_tone) * 2 ** self.octaves)

    def play(self, tone):
        self._check_open()
        self._tone = tone if isinstance(tone, Tone) else Tone(tone)

    def stop(self):
        self._tone = None

    @property
    def is_active(self):
        return self._tone is not None

    def close(self):
        self._tone = None
        super().close()

    def _board_info(self):
        return "TonalBuzzer", [self._pin], {self._pin: 1.0 if self._tone is not None else 0.0}


# -------- inputs

class _Events:
    """when_* attributes and wait_for_* for something that becomes active and inactive."""

    _on_name = "when_activated"
    _off_name = "when_deactivated"

    def _init_events(self):
        self._handlers = {}
        self._active = False
        self._since = core.now()

    def _handler_prop(name):  # noqa: N805
        def get(self):
            h = self._handlers.get(name)
            return h[0] if h else None

        def set_(self, value):
            h = _check_handler(value)
            if h is None:
                self._handlers.pop(name, None)
            else:
                self._handlers[name] = h
        return property(get, set_)

    when_activated = _handler_prop("activated")
    when_deactivated = _handler_prop("deactivated")

    def _set_active(self, active: bool):
        if active == self._active:
            return
        self._active = active
        self._since = core.now()
        self._held_fired = False
        _fire(self._handlers.get("activated" if active else "deactivated"), self)

    def wait_for_active(self, timeout=None):
        return core.wait_until(lambda: self._active, timeout)

    def wait_for_inactive(self, timeout=None):
        return core.wait_until(lambda: not self._active, timeout)


class DigitalInputDevice(_Events, GPIODevice):
    def __init__(self, pin=None, pull_up=False, active_state=None, bounce_time=None):
        super().__init__(pin)
        self._init_events()
        self.pull_up = pull_up
        self._held_fired = False

    @property
    def value(self):
        return int(self._active)

    @property
    def is_active(self):
        return self._active

    def _board_set(self, on):
        self._set_active(bool(on))

    def _board_info(self):
        return type(self).__name__, [self._pin], {self._pin: 1.0 if self._active else 0.0}


class Button(DigitalInputDevice):
    def __init__(self, pin=None, pull_up=True, active_state=None, bounce_time=None, hold_time=1, hold_repeat=False):
        super().__init__(pin, pull_up, active_state, bounce_time)
        self.hold_time = hold_time
        self.hold_repeat = hold_repeat
        self._next_hold = None

    def _handler_prop(name):  # noqa: N805
        return _Events._handler_prop(name)

    when_pressed = _handler_prop("activated")
    when_released = _handler_prop("deactivated")
    when_held = _handler_prop("held")

    @property
    def is_pressed(self):
        return self._active

    @property
    def is_held(self):
        return self._active and core.now() - self._since >= self.hold_time

    @property
    def held_time(self):
        return core.now() - self._since if self._active else None

    @property
    def pressed_time(self):
        return self.held_time

    def wait_for_press(self, timeout=None):
        return self.wait_for_active(timeout)

    def wait_for_release(self, timeout=None):
        return self.wait_for_inactive(timeout)

    def _set_active(self, active):
        if active and not self._active:
            self._next_hold = core.now() + self.hold_time
        super()._set_active(active)

    def _poll(self, t):
        if self._active and self._next_hold is not None and t >= self._next_hold and "held" in self._handlers:
            self._next_hold = t + self.hold_time if self.hold_repeat else None
            _fire(self._handlers.get("held"), self)
        elif not self._active:
            self._next_hold = None


class MotionSensor(DigitalInputDevice):
    def __init__(self, pin=None, pull_up=False, active_state=None, queue_len=1, sample_rate=10, threshold=0.5, partial=False):
        super().__init__(pin, pull_up, active_state)

    def _handler_prop(name):  # noqa: N805
        return _Events._handler_prop(name)

    when_motion = _handler_prop("activated")
    when_no_motion = _handler_prop("deactivated")

    @property
    def motion_detected(self):
        return self._active

    def wait_for_motion(self, timeout=None):
        return self.wait_for_active(timeout)

    def wait_for_no_motion(self, timeout=None):
        return self.wait_for_inactive(timeout)


class DistanceSensor(_Events, GPIODevice):
    def __init__(self, echo=None, trigger=None, queue_len=9, max_distance=1, threshold_distance=0.3, partial=False):
        if echo is None or trigger is None:
            raise GPIODeviceError("DistanceSensor needs echo and trigger pins")
        super().__init__(echo)
        try:
            self._trigger = GPIODevice(trigger)
        except Exception:
            super().close()
            raise
        self._init_events()
        self.max_distance = max_distance
        self.threshold_distance = threshold_distance
        self._in = False

    @property
    def echo(self):
        return self._pin

    @property
    def trigger(self):
        return self._trigger.pin

    @property
    def distance(self):
        self._check_open()
        return min(self.max_distance, core.distance_m.get(self._pin, 1.0))

    @property
    def value(self):
        return min(1.0, self.distance / self.max_distance)

    @property
    def in_range(self):
        return self.distance <= self.threshold_distance

    def _handler_prop(name):  # noqa: N805
        return _Events._handler_prop(name)

    when_in_range = _handler_prop("activated")
    when_out_of_range = _handler_prop("deactivated")

    @property
    def _active(self):
        return self.in_range

    @_active.setter
    def _active(self, v):
        pass

    def _poll(self, t):
        inside = self.in_range
        if inside != self._in:
            self._in = inside
            _fire(self._handlers.get("activated" if inside else "deactivated"), self)

    def wait_for_in_range(self, timeout=None):
        return core.wait_until(lambda: self.in_range, timeout)

    def wait_for_out_of_range(self, timeout=None):
        return core.wait_until(lambda: not self.in_range, timeout)

    def close(self):
        if not self._closed:
            self._trigger.close()
        super().close()

    def _board_info(self):
        return "DistanceSensor", [self._pin, self._trigger._pin], {self._pin: round(self.distance, 3)}

    def __repr__(self):
        return f"<gpiozero.DistanceSensor object on pins GPIO{self._pin} and GPIO{self._trigger._pin}>"


# ---------------------------------------------------------------- making `import gpiozero` find all this

_NAMES = [
    "GPIOZeroError", "DeviceClosed", "GPIODeviceError", "GPIODeviceClosed", "GPIOPinInUse", "PinError", "PinInvalidPin",
    "PinPWMUnsupported", "BadEventHandler", "OutputDeviceError", "OutputDeviceBadValue", "InputDeviceError", "BadPinFactory",
]
_PUBLIC = [
    "Pin", "Device", "GPIODevice", "OutputDevice", "DigitalOutputDevice", "PWMOutputDevice", "LED", "PWMLED", "Buzzer", "TonalBuzzer",
    "RGBLED", "LEDBoard", "LEDBarGraph", "Servo", "DigitalInputDevice", "Button", "MotionSensor", "DistanceSensor",
]


def install() -> None:
    """Make `import gpiozero` (and gpiozero.exc, gpiozero.tones) give these classes."""
    me = sys.modules[__name__]
    gz = types.ModuleType("gpiozero")
    exc = types.ModuleType("gpiozero.exc")
    tones = types.ModuleType("gpiozero.tones")
    for n in _NAMES:
        setattr(exc, n, getattr(me, n))
        setattr(gz, n, getattr(me, n))
    for n in _PUBLIC:
        setattr(gz, n, getattr(me, n))
    tones.Tone = gz.Tone = Tone
    gz.exc, gz.tones = exc, tones
    gz.__path__ = []
    for cls_name in _PUBLIC + _NAMES:
        getattr(me, cls_name).__module__ = "gpiozero.exc" if cls_name in _NAMES else "gpiozero"
    Tone.__module__ = "gpiozero.tones"
    sys.modules.update({"gpiozero": gz, "gpiozero.exc": exc, "gpiozero.tones": tones})
