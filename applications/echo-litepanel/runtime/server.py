#!/usr/bin/env python3
"""Echo-Mate device service for the existing LitePanel host (LP Binary v1)."""
import argparse
import asyncio
import contextlib
import json
import logging
from pathlib import Path
import signal
import socket
import time

from audio import Audio
from camera import Camera
from motors import Motors
from wifi import WifiSignal
import wire_protocol as wire

LOG = logging.getLogger('echo-litepanel')


class Discovery(asyncio.DatagramProtocol):
    def __init__(self, name, port):
        self.name, self.port = name, port

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, peer):
        if data != b'LITE_PANEL_DISCOVER_V1':
            return
        # The legacy discovery API intentionally uses JSON; TCP uses binary.
        self.transport.sendto(json.dumps(dict(v=1, type='discovery', name=self.name,
                                             id=self.name, port=self.port)).encode(), peer)


class Device:
    def __init__(self, motors=None, audio=None, camera=None, name=None):
        self.motors = motors if motors is not None else Motors()
        self.audio = audio if audio is not None else Audio()
        self.camera = camera if camera is not None else Camera()
        self.name = name or 'echo_mate_' + socket.gethostname()[-24:]
        self.active = None
        self.cap_seq = 0
        self.camera_process = None
        self.wifi = WifiSignal()

    def capabilities(self):
        modules = ['audio', 'camera']
        if self.motors.ready:
            modules.append('vehicle')
        return dict(version=1, name=self.name, signals=[], status=[], modules=modules)

    def status(self):
        return dict(data_source='real', direction=self.motors.direction,
                    **self.audio.status(), **self.wifi.status())

    async def command(self, key, value):
        if key == 'direction':
            self.motors.command(value)
        elif key in ('audio_playing', 'audio_volume', 'voice_listen', 'voice_talk'):
            await self.audio.command(key, value)
        elif key == 'speed':
            raise ValueError('speed_control_unavailable')
        else:
            raise ValueError('unsupported_command')

    async def handle_client(self, reader, writer):
        if self.active is not None:
            writer.close()
            await writer.wait_closed()
            return
        self.active = writer
        self.motors.stop()
        self.cap_seq = (self.cap_seq + 1) & 0xffffffff
        cap_seq = self.cap_seq
        ready = asyncio.Event()
        send_lock = asyncio.Lock()
        decoder = wire.Decoder()

        async def send(kind, payload, **fields):
            data = wire.encode(dict(v=1, type=kind, payload=payload, **fields))
            async with send_lock:
                writer.write(data)
                await asyncio.wait_for(writer.drain(), .5)

        async def declare():
            await send('capabilities', self.capabilities(), seq=cap_seq)

        async def updates():
            sequence = 0
            while True:
                await self.audio.tick()
                if ready.is_set():
                    # No synthetic sensor values: this is a control heartbeat.
                    await send('status', self.status())
                    await send('telemetry', dict(data_source='real', signals={},
                                                direction=self.motors.direction),
                               sample_seq=sequence, sample_time_us=int(time.monotonic() * 1e6))
                    sequence = (sequence + 1) & 0xffffffff
                else:
                    await declare()
                await asyncio.sleep(.25)

        async def microphone():
            while True:
                try:
                    payload = await self.audio.capture()
                    if payload and ready.is_set():
                        await send('audio', payload)
                except (asyncio.IncompleteReadError, OSError, ValueError) as error:
                    self.audio.error = str(error)
                    await self.audio.stop()

        update_task = asyncio.create_task(updates())
        microphone_task = asyncio.create_task(microphone())
        try:
            while True:
                read_task = asyncio.create_task(reader.read(4096))
                done, _ = await asyncio.wait([read_task, update_task, microphone_task],
                                             return_when=asyncio.FIRST_COMPLETED)
                if read_task not in done:
                    read_task.cancel()
                    await asyncio.gather(read_task, return_exceptions=True)
                    for task in (update_task, microphone_task):
                        if task in done:
                            task.result()
                    break
                data = read_task.result()
                if not data:
                    break
                for message in decoder.feed(data):
                    payload = message.get('payload')
                    if not isinstance(payload, dict):
                        continue
                    kind = message['type']
                    if kind == 'capabilities_request':
                        # A new handshake invalidates all existing actuation.
                        ready.clear()
                        self.motors.stop()
                        await self.audio.stop()
                        await declare()
                    elif kind == 'capabilities_ack':
                        if type(message.get('seq')) is int and message['seq'] == cap_seq and payload.get('ok') is True:
                            ready.set()
                    elif kind in ('command', 'set'):
                        sequence = message.get('seq')
                        if type(sequence) is not int or not 0 <= sequence <= 0xffffffff:
                            continue
                        try:
                            if not ready.is_set():
                                raise ValueError('capabilities_not_acknowledged')
                            if kind == 'set':
                                raise ValueError('settings_not_supported')
                            await self.command(payload.get('key'), payload.get('value'))
                            await send('ack', dict(ok=True), seq=sequence)
                            await send('status', self.status())
                        except (ValueError, OSError, asyncio.TimeoutError) as error:
                            await send('ack', dict(ok=False, error=str(error)), seq=sequence)
                    elif kind == 'audio' and ready.is_set():
                        try:
                            await self.audio.receive(payload)
                        except (ValueError, OSError, asyncio.TimeoutError) as error:
                            self.audio.error = str(error)
                            await self.audio.stop()
        except (OSError, ValueError, asyncio.TimeoutError) as error:
            LOG.info('Control connection ended: %s', error)
        finally:
            self.motors.stop()
            for task in (update_task, microphone_task):
                task.cancel()
            await asyncio.gather(update_task, microphone_task, return_exceptions=True)
            await self.audio.stop()
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            self.active = None

    async def supervise_camera(self, executable):
        while True:
            try:
                self.camera_process = await asyncio.create_subprocess_exec(
                    executable, stdout=asyncio.subprocess.DEVNULL)
                await asyncio.sleep(1)
                if self.camera_process.returncode is None:
                    self.camera.error = ''
                code = await self.camera_process.wait()
                self.camera.error = f'camera_process_exit_{code}'
            except OSError as error:
                self.camera.error = str(error)
            LOG.warning('Camera unavailable: %s; retrying in 10 seconds', self.camera.error)
            await asyncio.sleep(10)

    async def connect_cloud(self, config_path):
        from cloud import CloudLink, load_config
        while True:
            try:
                if Path(config_path).exists():
                    await CloudLink(self, load_config(config_path)).run()
            except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as error:
                LOG.warning('Cloud MQTT unavailable: %s', error)
            await asyncio.sleep(5)


async def main(args):
    device = Device(audio=Audio(args.audio_device), name=args.name)
    if not device.motors.ready:
        LOG.warning('Motor GPIO unavailable: %s', device.motors.error)
    Path('/tmp/echo-litepanel').mkdir(exist_ok=True)
    servers = device.camera.start_http(args.bind)
    udp = None
    camera_task = None
    cloud_task = None
    wifi_task = None
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        udp, _ = await loop.create_datagram_endpoint(lambda: Discovery(device.name, args.port),
                                                    local_addr=(args.bind, 9001), allow_broadcast=True)
        camera_task = asyncio.create_task(device.supervise_camera(args.camera))
        cloud_task = asyncio.create_task(device.connect_cloud(args.cloud_config))
        wifi_task = asyncio.create_task(device.wifi.run())
        async with await asyncio.start_server(device.handle_client, args.bind, args.port):
            LOG.info('LitePanel TCP %s:%d; camera HTTP 9002/9003', args.bind, args.port)
            await stop.wait()
    finally:
        device.motors.close()
        if device.active:
            device.active.close()
        await device.audio.stop()
        if wifi_task:
            wifi_task.cancel()
            await asyncio.gather(wifi_task, return_exceptions=True)
        if cloud_task:
            cloud_task.cancel()
            await asyncio.gather(cloud_task, return_exceptions=True)
        if camera_task:
            camera_task.cancel()
            await asyncio.gather(camera_task, return_exceptions=True)
        if device.camera_process and device.camera_process.returncode is None:
            device.camera_process.terminate()
            try:
                await asyncio.wait_for(device.camera_process.wait(), 2)
            except asyncio.TimeoutError:
                device.camera_process.kill()
                await device.camera_process.wait()
        if udp:
            udp.close()
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--name', default=None)
    parser.add_argument('--audio-device', default='plughw:0,0')
    parser.add_argument('--camera', default='/usr/bin/echo-camera')
    parser.add_argument('--cloud-config', default='/userdata/echo-litepanel/cloud.json')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(main(parser.parse_args()))
