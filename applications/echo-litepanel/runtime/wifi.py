"""Sample driver RSSI off the control loop; never reinterpret WEXT percentages."""
import asyncio
import re
import time


class WifiSignal:
    def __init__(self, interface='wlan0', clock=time.monotonic):
        self.interface, self.clock = interface, clock
        self.rssi, self.updated = None, None

    @staticmethod
    def parse(text):
        if not re.search(r'^Connected to ', text, re.MULTILINE):
            return None
        match = re.search(r'^\s*signal:\s*(-?\d+(?:\.\d+)?)\s*dBm\s*$', text, re.MULTILINE)
        if match:
            value = float(match.group(1))
            if -127 <= value <= 0:
                return value
        return None

    def status(self):
        age = int((self.clock() - self.updated) * 1000) if self.updated is not None else -1
        result = {'wifi_signal_age_ms': age}
        if self.rssi is not None and 0 <= age <= 15000:
            result['wifi_rssi'] = self.rssi
        return result

    async def run(self):
        while True:
            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    '/usr/sbin/iw', 'dev', self.interface, 'link',
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                output, _ = await asyncio.wait_for(process.communicate(), 1.5)
                value = self.parse(output.decode('utf-8', 'replace')) if process.returncode == 0 else None
                self.rssi = value
                self.updated = self.clock() if value is not None else None
            except (OSError, asyncio.TimeoutError):
                self.rssi, self.updated = None, None
            finally:
                if process and process.returncode is None:
                    process.kill()
                    await process.wait()
            await asyncio.sleep(5)
