"""grove.grove_relay: the Grove relay (it clicks on and off; its light shows on)."""
from gpiozero import DigitalOutputDevice


class GroveRelay(DigitalOutputDevice):
    def __init__(self, pin):
        super().__init__(pin)
