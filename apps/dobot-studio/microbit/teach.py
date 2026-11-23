"""Flash this script onto a BBC micro:bit with the MicroPython editor."""
from microbit import accelerometer, button_a, button_b, display, running_time, sleep, uart

uart.init(baudrate=115200)
display.show("T")
last = "-"
started = 0
sent = False
chord = False
while True:
    a = button_a.is_pressed()
    b = button_b.is_pressed()
    state = "AB" if a and b else "A" if a else "B" if b else "-"
    if state != last:
        last, started, sent = state, running_time(), False
    action = "-"
    if state == "AB":
        chord = True
    elif state == "-":
        chord = False
    if state in ("A", "B") and not chord and not sent and running_time() - started >= 160:
        action, sent = state, True
    x, y, z = accelerometer.get_values()
    line = "DT1,{},{},{},{},{}\n".format(x, y, z, int(state == "AB"), action)
    uart.write(line)
    sleep(55)
