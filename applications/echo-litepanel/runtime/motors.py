"""Original Echo-Mate two-motor wiring, with an independent expiry watchdog."""
from pathlib import Path
import threading
import time


class Motors:
    PINS = (32, 33, 35, 36)  # GPIO1_A0, A1, A3, A4
    LEVELS = {'stop': (0, 0, 0, 0), 'forward': (0, 1, 1, 0),
              'backward': (1, 0, 0, 1), 'left': (1, 0, 1, 0),
              'right': (0, 1, 0, 1)}

    def __init__(self, root='/sys/class/gpio', clock=time.monotonic):
        self.root, self.clock = Path(root), clock
        self.lock = threading.Lock()
        self.direction, self.deadline = 'stop', 0
        self.error = ''
        self.ready = False
        self.closed = threading.Event()
        try:
            for pin in self.PINS:
                folder = self.root / f'gpio{pin}'
                if not folder.exists():
                    (self.root / 'export').write_text(str(pin))
                # Atomic direction+initial level avoids briefly driving high.
                (folder / 'direction').write_text('low')
            self.ready = True
            self._write(self.LEVELS['stop'])
        except OSError as error:
            self.error = str(error)
            self._best_effort_stop()
        self.thread = threading.Thread(target=self._watchdog, daemon=True)
        self.thread.start()

    def _write(self, levels):
        # Always de-energize both bridges before changing polarity.
        for pin in self.PINS:
            (self.root / f'gpio{pin}/value').write_text('0')
        if any(levels):
            time.sleep(.002)
            for pin, level in zip(self.PINS, levels):
                if level:
                    (self.root / f'gpio{pin}/value').write_text('1')

    def _best_effort_stop(self):
        for pin in self.PINS:
            try:
                (self.root / f'gpio{pin}/value').write_text('0')
            except OSError:
                pass
        self.direction, self.deadline = 'stop', 0

    def command(self, direction):
        if not isinstance(direction, str) or direction not in self.LEVELS:
            raise ValueError('invalid_direction')
        with self.lock:
            if not self.ready:
                raise ValueError('vehicle_driver_unavailable')
            try:
                if direction != self.direction:
                    self._write(self.LEVELS[direction])
                self.direction = direction
                self.deadline = self.clock() + .7 if direction != 'stop' else 0
            except OSError as error:
                self.ready, self.error = False, str(error)
                self._best_effort_stop()
                raise ValueError('vehicle_driver_error') from error

    def expire(self):
        with self.lock:
            if self.deadline and self.clock() >= self.deadline:
                self._best_effort_stop()

    def _watchdog(self):
        while not self.closed.wait(.025):
            self.expire()

    def stop(self):
        with self.lock:
            self._best_effort_stop()

    def close(self):
        self.closed.set()
        self.thread.join(timeout=1)
        self.stop()
