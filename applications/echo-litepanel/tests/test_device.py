import asyncio
import base64
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / 'runtime'))
from motors import Motors
from audio import Audio
from camera import Camera
from cloud import load_config, MessageReader, HEADER, CHUNK
from server import Device
from wifi import WifiSignal
import wire_protocol as wire


class FakeAudio(Audio):
    async def capture(self):
        await asyncio.sleep(.02)
        return None

    async def command(self, key, value):
        if key == 'audio_volume':
            await super().command(key, value)
        else:
            setattr(self, {'voice_listen': 'listen', 'voice_talk': 'talk', 'audio_playing': 'playing'}[key], value)


def gpio_fixture(folder):
    root = Path(folder)
    for pin in Motors.PINS:
        path = root / f'gpio{pin}'
        path.mkdir()
        (path / 'direction').touch()
        (path / 'value').write_text('0')
    return root


class HardwareTests(unittest.TestCase):
    def test_wifi_uses_dbm_and_expires_missing_signal(self):
        self.assertEqual(WifiSignal.parse('Connected to 00:11:22:33:44:55 (on wlan0)\n\tsignal: -45 dBm\n'), -45)
        self.assertIsNone(WifiSignal.parse('Not connected.\n'))
        self.assertIsNone(WifiSignal.parse('Connected to ap\n signal: 100 dBm\n'))
        self.assertIsNone(WifiSignal.parse('wlan0: 0000 88. 100. 0.'))
        now = [10.]
        wifi = WifiSignal(clock=lambda: now[0])
        self.assertEqual(wifi.status(), {'wifi_signal_age_ms': -1})
        wifi.rssi, wifi.updated = -45, now[0]
        self.assertEqual(wifi.status()['wifi_rssi'], -45)
        now[0] += 16
        self.assertNotIn('wifi_rssi', wifi.status())

    def test_native_websocket_mask_round_trip(self):
        from paho.mqtt.client import _WebsocketWrapper
        for size in (0, 1, 3, 4, 125, 126, 65535, 65536):
            payload = bytes((i % 256 for i in range(size)))
            frame = _WebsocketWrapper._create_frame(None, 2, bytearray(payload))
            self.assertEqual(frame[0], 0x82)
            self.assertTrue(frame[1] & 0x80)
            offset = 2 if size < 126 else 4 if size < 65536 else 10
            mask = frame[offset:offset + 4]
            decoded = bytes(byte ^ mask[i % 4] for i, byte in enumerate(frame[offset + 4:]))
            self.assertEqual(decoded, payload)

    def test_motor_original_polarity_watchdog_and_disconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            root = gpio_fixture(folder)
            now = [100.]
            motors = Motors(root, clock=lambda: now[0])
            try:
                self.assertTrue(motors.ready)
                for direction in ('forward', 'backward', 'left', 'right'):
                    motors.command(direction)
                    actual = tuple(int((root / f'gpio{pin}/value').read_text()) for pin in Motors.PINS)
                    self.assertEqual(actual, Motors.LEVELS[direction])
                now[0] += .71
                motors.expire()
                self.assertEqual(motors.direction, 'stop')
                self.assertEqual(tuple(int((root / f'gpio{pin}/value').read_text()) for pin in Motors.PINS), (0, 0, 0, 0))
                motors.command('forward')
                motors.stop()
                self.assertEqual(motors.direction, 'stop')
            finally:
                motors.close()

    def test_gpio_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            motors = Motors(folder)
            try:
                self.assertFalse(motors.ready)
                with self.assertRaisesRegex(ValueError, 'vehicle_driver_unavailable'):
                    motors.command('forward')
            finally:
                motors.close()

    def test_camera_never_returns_stale_or_fake_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'frame.jpg'
            camera = Camera(path)
            self.assertFalse(camera.status()['ready'])
            path.write_bytes(b'\xff\xd8test\xff\xd9')
            self.assertTrue(camera.status()['ready'])
            os.utime(path, (time.time() - 4, time.time() - 4))
            with self.assertRaisesRegex(ValueError, 'stale'):
                camera.snapshot()

    def test_pcm_volume(self):
        audio = Audio()
        audio.volume = 50
        self.assertEqual(audio._scale(struct.pack('<hhh', -30000, 0, 30000)), struct.pack('<hhh', -15000, 0, 15000))


class AudioStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_stalled_player_shutdown_fits_control_deadline(self):
        killed = asyncio.Event()

        class Pipe:
            def close(self):
                pass

        class Player:
            returncode = None
            stdin = Pipe()

            def terminate(self):
                pass

            def kill(self):
                self.returncode = -9
                killed.set()

            async def wait(self):
                await killed.wait()
                return self.returncode

        await asyncio.wait_for(Audio()._kill(Player()), .2)
        self.assertTrue(killed.is_set())

    async def test_slow_speaker_does_not_block_control_reader(self):
        stalled = asyncio.Event()

        class Pipe:
            def write(self, pcm):
                pass

            async def drain(self):
                await stalled.wait()

        class Player:
            returncode = None
            stdin = Pipe()

        audio = Audio()
        audio.player, audio.talk = Player(), True
        payload = dict(codec='pcm_s16le', sample_rate=16000,
                       data=base64.b64encode(bytes(1024)).decode())
        audio.speaker_task = asyncio.create_task(audio._speaker())
        try:
            await asyncio.sleep(.11)
            for _ in range(20):
                await asyncio.wait_for(audio.receive(payload), .05)
            self.assertEqual(audio.rx, 20)
            self.assertLessEqual(audio.speaker_queue.qsize(), 8)
        finally:
            await audio._stop_speaker()
        self.assertIsNone(audio.speaker_task)
        self.assertTrue(audio.speaker_queue.empty())


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.motors = Motors(gpio_fixture(self.folder.name))
        self.device = Device(self.motors, FakeAudio(), Camera(Path(self.folder.name) / 'frame.jpg'), 'echo_test')
        self.server = await asyncio.start_server(self.device.handle_client, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.reader, self.writer = await asyncio.open_connection('127.0.0.1', self.port)
        self.decoder = wire.Decoder()
        self.messages = []

    async def asyncTearDown(self):
        self.writer.close()
        await self.writer.wait_closed()
        await asyncio.sleep(.08)
        self.server.close()
        await self.server.wait_closed()
        self.motors.close()
        self.folder.cleanup()

    async def receive(self, kind, seq=None):
        async def read():
            while True:
                for index, item in enumerate(self.messages):
                    if item['type'] == kind and (seq is None or item.get('seq') == seq):
                        return self.messages.pop(index)
                data = await self.reader.read(4096)
                if not data:
                    raise EOFError()
                self.messages.extend(self.decoder.feed(data))
        return await asyncio.wait_for(read(), 2)

    async def send(self, kind, payload, seq=1):
        self.writer.write(wire.encode(dict(v=1, type=kind, payload=payload, seq=seq)))
        await self.writer.drain()

    async def handshake(self):
        cap = await self.receive('capabilities')
        self.assertEqual(cap['payload']['modules'], ['audio', 'camera', 'vehicle'])
        await self.send('capabilities_ack', {'ok': True}, cap['seq'])
        return await self.receive('telemetry')

    async def test_handshake_rejection_crc_motion_and_expiry(self):
        cap = await self.receive('capabilities')
        await self.send('command', {'key': 'direction', 'value': 'forward'}, 10)
        self.assertFalse((await self.receive('ack', 10))['payload']['ok'])
        await self.send('capabilities_ack', {'ok': True}, cap['seq'])
        await self.receive('telemetry')
        bad = bytearray(wire.encode(dict(v=1, type='command', seq=11, payload={'key': 'direction', 'value': 'forward'})))
        bad[-1] ^= 1
        self.writer.write(bad)
        await asyncio.sleep(.05)
        self.assertEqual(self.motors.direction, 'stop')
        await self.send('command', {'key': 'direction', 'value': 'forward'}, 12)
        self.assertTrue((await self.receive('ack', 12))['payload']['ok'])
        self.assertEqual(self.motors.direction, 'forward')
        await asyncio.sleep(.76)
        self.assertEqual(self.motors.direction, 'stop')
        await self.send('command', {'key': 'speed', 'value': 20}, 13)
        self.assertFalse((await self.receive('ack', 13))['payload']['ok'])

    async def test_disconnect_stops_and_telemetry_has_no_fake_measurements(self):
        sample = await self.handshake()
        self.assertEqual(sample['payload']['signals'], {})
        self.assertNotIn('battery', sample['payload'])
        await self.send('command', {'key': 'direction', 'value': 'left'}, 14)
        await self.receive('ack', 14)
        self.writer.close()
        await self.writer.wait_closed()
        await asyncio.sleep(.08)
        self.assertEqual(self.motors.direction, 'stop')

    async def test_cloud_reader_discards_congested_commands(self):
        reader = MessageReader()
        reader.feed(b'old')
        await asyncio.sleep(.26)
        self.assertEqual(await reader.read(4096), b'')

    async def test_cloud_reader_drops_old_speech_without_losing_fresh_control(self):
        reader = MessageReader()
        reader.feed(wire.encode(dict(v=1, type='audio', payload={})))
        await asyncio.sleep(.26)
        stop = wire.encode(dict(v=1, type='command', seq=99,
                                payload={'key': 'direction', 'value': 'stop'}))
        reader.feed(stop)
        self.assertEqual(await reader.read(4096), stop)
        self.assertFalse(reader.closed)

    async def test_listen_toggle_does_not_stop_new_speaker_session(self):
        class Recorder:
            returncode = None
            stdout = asyncio.StreamReader()
        audio = Audio()
        audio.recorder = Recorder()
        capture = asyncio.create_task(audio.capture())
        await asyncio.sleep(.01)
        old = audio.recorder
        audio.recorder = None
        audio.talk = True
        old.stdout.feed_eof()
        self.assertIsNone(await capture)
        self.assertTrue(audio.talk)


class CompatibilityTests(unittest.TestCase):
    def test_exact_host_schema_and_camera_reassembly(self):
        host = Path(os.environ.get('LITEPANEL_SOURCE', str(APP.parents[2] / 'lite-panel')))
        if not host.exists():
            self.skipTest('Set LITEPANEL_SOURCE to test against the actual host')
        self.assertEqual((APP / 'runtime/wire_schema.json').read_bytes(),
                         (host / 'wire_schema.json').read_bytes())
        spec = importlib.util.spec_from_file_location('host_wire', host / 'wire_protocol.py')
        host_wire = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(host_wire)
        self.assertEqual(wire.crc16(b'123456789'), 0x29b1)
        for payload in ({}, {'key': 'direction', 'value': 'stop'},
                        {'codec': 'pcm_s16le', 'sample_rate': 16000,
                         'data': base64.b64encode(bytes(range(256)) * 4).decode()}):
            for kind in wire.TYPES:
                message = dict(v=1, type=kind, seq=4294967295, payload=payload)
                encoded = wire.encode(message)
                self.assertEqual(encoded, host_wire.encode(message))
                self.assertEqual(host_wire.decode(encoded), wire.decode(encoded))
        spec = importlib.util.spec_from_file_location('host_camera', host / 'mqtt_camera.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        receiver = module.CameraFrames()
        jpeg = b'\xff\xd8' + b'x' * 100000 + b'\xff\xd9'
        count = (len(jpeg) + CHUNK - 1) // CHUNK
        for index in range(count):
            receiver.feed(HEADER.pack(b'LPJ1', 8, index, count, len(jpeg)) + jpeg[index*CHUNK:(index+1)*CHUNK])
        self.assertEqual(receiver.snapshot()[0], jpeg)


if __name__ == '__main__':
    unittest.main()
