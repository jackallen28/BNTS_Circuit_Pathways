"""cpsim: what a student's Python program needs from a Raspberry Pi, in the browser.

The browser can't run threads or touch pins, so this package pretends: a small scheduler
(core.py) lets time.sleep(), signal.pause() and the waits in gpiozero look after button
presses and blinking lights, and a gpiozero look-alike (gpiozero_sim.py) keeps its parts in
memory and reports them to the on-screen board. The page talks to it through the host
module (_cp_host), which the page provides.
"""
