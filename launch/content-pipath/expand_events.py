from __future__ import annotations

def expand_events(events: list | None) -> list[tuple[float, str]]:
    """Turn a step's demo_events into timed shim commands.

    "1.5 press 23" / "1.8 release 23"     one command at 1.5 s / 1.8 s
    "2 tap 23"                            press, then release 0.2 s later
    "1 tap 23 every 0.8 until 30"         keep tapping (for games with random waits)
    "1.5 distance 26 15"                  the distance sensor on echo GPIO26 sees something 15 cm away
    """
    out: list[tuple[float, str]] = []
    for ev in events or []:
        w = str(ev).split()
        t, action = float(w[0]), w[1]
        args = w[2:w.index("every")] if "every" in w else w[2:]       # "distance 26 15": a pin and a value
        pin = args[0]
        every = float(w[w.index("every") + 1]) if "every" in w else None
        until = float(w[w.index("until") + 1]) if "until" in w else t
        times = [t] if not every else [t + i * every for i in range(int((until - t) / every) + 1)]
        for x in times:
            if action == "tap":
                out += [(x, f"press {pin}"), (x + 0.2, f"release {pin}")]
            else:
                out.append((x, " ".join([action, *args])))
    return sorted(out)
