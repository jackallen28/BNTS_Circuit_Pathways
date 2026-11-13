"""grove.grove_rotary_angle_sensor: the Grove knob."""
from grove.adc import _Analog


class GroveRotaryAngleSensor(_Analog):
    kind = "RotaryAngle"

    @property
    def value(self):
        """How far the knob is turned: 0 to 999."""
        return self.adc.read(self.channel)
