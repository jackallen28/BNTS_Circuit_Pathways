"""grove.grove_light_sensor_v1_2: the Grove light sensor."""
from grove.adc import _Analog


class GroveLightSensor(_Analog):
    kind = "Light"

    @property
    def light(self):
        """How bright it is: 0 (dark) to 999 (bright)."""
        return self.adc.read(self.channel)
