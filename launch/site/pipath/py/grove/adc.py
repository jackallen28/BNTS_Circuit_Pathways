"""grove.adc: the Base Hat's analog ports (A0, A2, A4, A6), read as 0 to 999."""
from cpsim import core


class ADC:
    def __init__(self, address=0x04):
        self.address = address

    def read(self, channel):
        """The reading on a channel, from 0 (none) to 999 (full)."""
        return core.analog.get(int(channel), 500)

    def read_voltage(self, channel):
        """The voltage on a channel, in millivolts (the Base Hat runs at 3.3V)."""
        return round(self.read(channel) * 3300 / 999)

    def read_raw(self, channel):
        return round(self.read(channel) * 4095 / 999)


class _Analog:
    """A Grove sensor on an analog port: it shows a slider on the on-screen board."""

    kind = "Analog"

    def __init__(self, channel):
        self.channel = int(channel)
        self.adc = ADC()
        self._closed = False
        core.devices.append(self)

    @property
    def closed(self):
        return self._closed

    def close(self):
        self._closed = True

    def _board_info(self):
        return self.kind, [self.channel], {}
