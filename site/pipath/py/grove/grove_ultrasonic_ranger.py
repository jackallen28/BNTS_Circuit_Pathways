"""grove.grove_ultrasonic_ranger: the Grove Ultrasonic Ranger, on one digital port."""
from cpsim import core
from gpiozero import GPIODevice


class GroveUltrasonicRanger(GPIODevice):
    def __init__(self, pin):
        super().__init__(pin)

    def get_distance(self):
        """The distance to the nearest thing in front, in centimetres."""
        self._check_open()
        return round(core.distance_m.get(self._pin, 1.0) * 100, 1)

    def _board_info(self):
        return "GroveUltrasonicRanger", [self._pin], {self._pin: core.distance_m.get(self._pin, 1.0)}
