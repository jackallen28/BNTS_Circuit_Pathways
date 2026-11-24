"""A fake Dobot Magician on a pseudo-terminal that speaks the real serial protocol."""
import os
import pty
import struct
import threading
import time
import tty

from dobot_studio import robot as R


class FakeDobot(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.master, slave = pty.openpty(); tty.setraw(self.master); tty.setraw(slave)
        self.path = os.ttyname(slave); self._slave = slave
        self.pose = [200.0, 0.0, 50.0, 0.0]; self.target = None
        self.queue = []; self.index = 0; self.running = False; self.alarm = False
        self.log = []; self.suction = None; self.gripper = None; self.home = (200., 0., 50., 0.)
        self.drop_next = 0; self.alive = True
        self.speed = 0.6      # mm per 3 ms tick, about 200 mm/s. Tests that only need to arrive raise it.
    def close(self):
        self.alive = False
        self.join(timeout=2)

    def run(self):
        buf = bytearray()
        while self.alive:
            time.sleep(0.003)
            self._advance()
            try: buf += os.read(self.master, 256)
            except OSError: continue
            while True:
                i = buf.find(R.HEADER)
                if i < 0 or len(buf) < i + 3: break
                n = buf[i+2]
                if len(buf) < i + 4 + n: break
                payload = bytes(buf[i+3:i+3+n]); del buf[:i+4+n]
                self._handle(payload[0], payload[1], payload[2:])
    def _advance(self):
        if self.running and self.queue:
            kind, tgt, idx = self.queue[0]
            step = self.speed
            cur = self.pose
            d = [t - c for c, t in zip(cur, tgt)]
            dist = sum(x*x for x in d[:3]) ** .5
            if dist <= step and abs(d[3]) <= step:
                self.pose = list(tgt); self.queue.pop(0); self.index = idx
            else:
                f = step / max(dist, 1e-9); self.pose = [c + x*f for c, x in zip(cur, d[:3])] + [cur[3] + d[3]*min(1, step/max(abs(d[3]),1e-9))]
    def _reply(self, cmd, ctrl, params=b""):
        payload = bytes((cmd, ctrl)) + params
        os.write(self.master, R.HEADER + bytes((len(payload),)) + payload + bytes((-sum(payload) & 0xff,)))
    def _handle(self, cmd, ctrl, params):
        self.log.append((cmd, ctrl, params))
        if self.drop_next:
            self.drop_next -= 1; return
        if cmd == R.GET_POSE: self._reply(cmd, ctrl, struct.pack("<8f", *self.pose, 0, 0, 0, 0))
        elif cmd == R.GET_ALARMS: self._reply(cmd, ctrl, bytes([1 if self.alarm else 0]) + bytes(15))
        elif cmd == R.GET_HOME: self._reply(cmd, ctrl, struct.pack("<4f", *self.home))
        elif cmd in (R.MOVE, R.HOME):
            self.index_next = getattr(self, "index_next", 0) + 1
            tgt = list(self.home) if cmd == R.HOME else list(struct.unpack("<4f", params[1:17]))
            self.queue.append((cmd, tgt, self.index_next)); self._reply(cmd, ctrl, struct.pack("<Q", self.index_next))
        elif cmd == R.QUEUE_INDEX: self._reply(cmd, ctrl, struct.pack("<Q", self.index))
        elif cmd == R.QUEUE_START: self.running = True; self._reply(cmd, ctrl)
        elif cmd in (R.QUEUE_STOP,): self.running = False; self._reply(cmd, ctrl)
        elif cmd == R.QUEUE_FORCE_STOP: self.running = False; self._reply(cmd, ctrl)
        elif cmd == R.QUEUE_CLEAR: self.queue.clear(); self._reply(cmd, ctrl)
        elif cmd == R.SUCTION: self.suction = params[1]; self._reply(cmd, ctrl)
        elif cmd == R.GRIPPER: self.gripper = params[1]; self._reply(cmd, ctrl)
        else: self._reply(cmd, ctrl)
