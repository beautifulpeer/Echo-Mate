"""Optional end-to-end test against a real temporary loopback Mosquitto broker."""
import asyncio
import base64
import importlib
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

from test_device import APP, FakeAudio, gpio_fixture
from motors import Motors
from camera import Camera
from server import Device
from cloud import CloudLink


class MQTTTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        host = Path(os.environ.get('LITEPANEL_SOURCE', ''))
        command = os.environ.get('ECHO_MQTT_BROKER_COMMAND') or shutil.which('mosquitto')
        if not command or not (host / 'connections.py').exists():
            self.skipTest('Set LITEPANEL_SOURCE and ECHO_MQTT_BROKER_COMMAND for real Broker integration')
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        config = self.path / 'mosquitto.conf'
        config.write_text(f'listener {self.port} 127.0.0.1\nallow_anonymous true\npersistence false\n')
        self.broker = subprocess.Popen(shlex.split(command) + ['-c', str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                _, writer = await asyncio.open_connection('127.0.0.1', self.port)
                writer.close()
                await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(.05)
        else:
            self.broker.terminate()
            self.broker.wait()
            self.fail('Temporary MQTT Broker did not start')
        gpio = self.path / 'gpio'
        gpio.mkdir()
        self.motors = Motors(gpio_fixture(gpio))
        self.camera = Camera(self.path / 'frame.jpg')
        self.device = Device(self.motors, FakeAudio(), self.camera, 'echo_test_mqtt')
        self.link = CloudLink(self.device, dict(host='127.0.0.1', port=self.port, tls=False,
                                               device_id='echo-test', camera_fps=2))
        self.cloud_task = asyncio.create_task(self.link.run())
        sys.path.append(str(host))
        connections = importlib.import_module('connections')
        self.host = connections.Session(dict(kind='mqtt', host='127.0.0.1', port=self.port,
                                             tls=False, up_topic=self.link.up, down_topic=self.link.down))
        self.host.thread = threading.Thread(target=self.host.run, daemon=True)
        self.host.thread.start()

    async def asyncTearDown(self):
        self.host.stop.set()
        self.cloud_task.cancel()
        await asyncio.gather(self.cloud_task, return_exceptions=True)
        await asyncio.to_thread(self.host.thread.join, 2)
        self.motors.close()
        self.broker.terminate()
        await asyncio.to_thread(self.broker.wait, 3)
        self.folder.cleanup()

    async def until(self, condition):
        for _ in range(120):
            if condition():
                return
            if self.cloud_task.done():
                self.cloud_task.result()
            await asyncio.sleep(.05)
        self.fail('Timed out waiting for MQTT state: ' + self.host.error)

    async def test_actual_host_handshake_motion_jpeg_and_disconnect(self):
        await self.until(lambda: self.host.received > 0)
        self.assertIn('vehicle', self.host.values['capabilities']['modules'])
        self.assertEqual(self.host.values['data_source'], 'real')
        command = self.host.send('direction', 'forward')
        await self.until(lambda: any(item['seq'] == command['seq'] and item['status'] == 'confirmed'
                                    for item in self.host.command_results))
        self.assertEqual(self.motors.direction, 'forward')
        jpeg = b'\xff\xd8' + b'x' * 100000 + b'\xff\xd9'
        self.camera.path.write_bytes(jpeg)
        await self.until(lambda: self.host.camera.frame is not None)
        self.assertEqual(self.host.camera.snapshot()[0], jpeg)
        self.cloud_task.cancel()
        await asyncio.gather(self.cloud_task, return_exceptions=True)
        self.assertEqual(self.motors.direction, 'stop')

    async def test_cloud_audio_with_patched_host(self):
        import inspect
        if "not in ('wifi', 'mqtt')" not in inspect.getsource(self.host.send_audio):
            self.skipTest('Original host intentionally rejects MQTT audio; test the generated patch copy')
        await self.until(lambda: self.host.received > 0)
        received = []
        payload = {'codec': 'pcm_s16le', 'sample_rate': 16000,
                   'data': base64.b64encode(b'\x01\0' * 512).decode()}

        async def receive(value):
            received.append(value)

        sent = [False]

        async def capture():
            await asyncio.sleep(.03)
            if self.device.audio.listen and not sent[0]:
                sent[0] = True
                return payload

        self.device.audio.receive = receive
        self.device.audio.capture = capture
        self.host.send_audio(payload)
        await self.until(lambda: bool(received))
        self.assertEqual(received[0], payload)
        self.host.send('voice_listen', True)
        await self.until(lambda: bool(self.host.audio_in))
        self.assertEqual(self.host.receive_audio()[0], payload)
