"""grove.grove_moisture_sensor: the Grove moisture sensor."""
from grove.adc import _Analog


class GroveMoistureSensor(_Analog):
    kind = "Moisture"

    @property
    def moisture(self):
        """How wet the soil is: 0 (dry) up to 999 (in water)."""
        return self.adc.read(self.channel)
