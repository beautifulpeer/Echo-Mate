"""Outbound MQTT transport; reuses the same binary device session as local TCP."""
import asyncio
import json
import logging
from pathlib import Path
import ssl
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).with_name('vendor')))
import paho.mqtt.client as mqtt

LOG = logging.getLogger('echo-litepanel.cloud')
HEADER = struct.Struct('!4sIHHI')
CHUNK = 48 * 1024


def load_config(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict) or not isinstance(value.get('host'), str) or not value['host'].strip():
        raise ValueError('cloud.host must be your actual MQTT broker address')
    identifier = value.get('device_id', 'echo-mate001')
    if not isinstance(identifier, str) or not identifier or len(identifier) > 64 or any(c in identifier for c in '/+#\x00'):
        raise ValueError('invalid cloud.device_id')
    tls = value.get('tls', True)
    if type(tls) is not bool:
        raise ValueError('cloud.tls must be boolean')
    port = value.get('port', 8883 if tls else 1883)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid MQTT port')
    fps = value.get('camera_fps', 2)
    if type(fps) not in (int, float) or not 0 <= fps <= 20:
        raise ValueError('camera_fps must be 0..20')
    transport = value.get('transport', 'tcp')
    if transport not in ('tcp', 'websockets'):
        raise ValueError('cloud.transport must be tcp or websockets')
    for key in ('username', 'password', 'ca_file'):
        if key in value and not isinstance(value[key], str):
            raise ValueError(f'cloud.{key} must be a string')
    return dict(value, device_id=identifier, tls=tls, port=port, camera_fps=fps)


class MessageReader:
    def __init__(self):
        self.queue = asyncio.Queue(maxsize=32)
        self.closed = False

    def feed(self, data):
        if self.closed:
            return
        if len(data) > 65545:
            self.close()
            return
        try:
            self.queue.put_nowait((time.monotonic(), data))
        except asyncio.QueueFull:
            LOG.warning('MQTT input queue full; closing control session')
            self.close()

    def close(self):
        self.closed = True
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait((0, b''))

    async def read(self, _size):
        while True:
            created, data = await self.queue.get()
            # Old speech may be dropped. Old control commands still close the
            # session rather than risk executing delayed motion.
            if created and time.monotonic() - created > .25:
                if len(data) >= 9 and data[:2] == b'\xa5\x5a' and data[3] == 1 and data[8] == 2:
                    continue
                LOG.warning('MQTT input delayed %.3fs; closing control session',
                            time.monotonic() - created)
                self.close()
                return b''
            return data


class MessageWriter:
    def __init__(self, link, reader):
        self.link, self.reader = link, reader
        self.pending = None

    def write(self, data):
        if self.reader.closed:
            raise ConnectionError('MQTT disconnected')
        self.pending = data

    async def drain(self):
        if self.pending is not None:
            data, self.pending = self.pending, None
            await self.link.publish(self.link.up, data)

    def close(self):
        self.reader.close()

    async def wait_closed(self):
        pass


class CloudLink:
    def __init__(self, device, config):
        self.device, self.config = device, config
        self.up = f'devices/{config["device_id"]}/up'
        self.down = f'devices/{config["device_id"]}/down'
        self.reader = self.session_task = None
        self.connected = asyncio.Event()
        self.ended = asyncio.Event()
        self.loop = asyncio.get_running_loop()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=config['device_id'], clean_session=True, reconnect_on_failure=False,
                                  transport=config.get('transport', 'tcp'))
        if config.get('transport') == 'websockets':
            self.client.ws_set_options(path=config.get('ws_path', '/mqtt'))
        self.client.connect_timeout = 5
        self.client.max_queued_messages_set(8)
        self.client.max_inflight_messages_set(2)
        self.client.reconnect_delay_set(1, 30)
        if config.get('username'):
            self.client.username_pw_set(config['username'], config.get('password', ''))
        if config['tls']:
            default_ca = Path(__file__).with_name('vendor') / 'ca-bundle.crt'
            self.client.tls_set(ca_certs=config.get('ca_file') or str(default_ca), tls_version=ssl.PROTOCOL_TLS_CLIENT)
        self.client.on_connect = self._connect
        self.client.on_disconnect = self._disconnect
        self.client.on_subscribe = self._subscribed
        self.client.on_message = self._message
        self.client.on_connect_fail = lambda client, userdata: self.loop.call_soon_threadsafe(self.ended.set)

    def _connect(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
            LOG.error('MQTT connect rejected: %s', reason)
            self.loop.call_soon_threadsafe(self.ended.set)
            return
        client.subscribe(self.down, qos=0)

    def _subscribed(self, client, userdata, mid, reasons, properties):
        if any(reason.is_failure for reason in reasons):
            LOG.error('MQTT command subscription rejected')
            self.loop.call_soon_threadsafe(self.ended.set)
            return
        self.loop.call_soon_threadsafe(self._start_session)

    def _start_session(self):
        if self.device.active is not None:
            LOG.warning('Another control session is active; MQTT will reconnect')
            self.ended.set()
            return
        self.reader = MessageReader()
        writer = MessageWriter(self, self.reader)
        self.connected.set()
        self.session_task = asyncio.create_task(self.device.handle_client(self.reader, writer))
        LOG.info('Cloud MQTT ready: %s:%d, %s', self.config['host'], self.config['port'], self.up)

    def _disconnect(self, client, userdata, flags, reason, properties):
        self.loop.call_soon_threadsafe(self._end_session)

    def _end_session(self):
        self.connected.clear()
        self.ended.set()
        self.device.motors.stop()
        if self.reader:
            self.reader.close()

    def _message(self, client, userdata, message):
        # Retained movement/audio commands must never be replayed on connection.
        if message.topic == self.down and not message.retain and self.reader:
            self.loop.call_soon_threadsafe(self.reader.feed, bytes(message.payload))

    async def publish(self, topic, data):
        if not self.connected.is_set():
            raise ConnectionError('MQTT not connected')
        info = self.client.publish(topic, data, qos=0, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f'MQTT publish error {info.rc}')
        await asyncio.to_thread(info.wait_for_publish, .4)
        if not info.is_published():
            raise TimeoutError('MQTT publish congested')

    async def camera_frames(self):
        sequence = 0
        while True:
            started = self.loop.time()
            await self.connected.wait()
            fps = self.config['camera_fps']
            if fps:
                try:
                    jpeg, _ = await asyncio.to_thread(self.device.camera.snapshot)
                    count = (len(jpeg) + CHUNK - 1) // CHUNK
                    for index in range(count):
                        packet = HEADER.pack(b'LPJ1', sequence, index, count, len(jpeg))
                        await self.publish(self.up + '/camera', packet + jpeg[index * CHUNK:(index + 1) * CHUNK])
                    sequence = (sequence + 1) & 0xffffffff
                except (OSError, ValueError, asyncio.TimeoutError):
                    pass
            await asyncio.sleep(max(0, 1 / fps - (self.loop.time() - started)) if fps else 1)

    async def run(self):
        self.client.connect_async(self.config['host'], self.config['port'], keepalive=10)
        self.client.loop_start()
        frames = asyncio.create_task(self.camera_frames())
        try:
            while not self.ended.is_set():
                await asyncio.sleep(.25)
                if self.session_task and self.session_task.done():
                    self.session_task.result()
                    break
        finally:
            frames.cancel()
            await asyncio.gather(frames, return_exceptions=True)
            self._end_session()
            if self.session_task:
                await asyncio.gather(self.session_task, return_exceptions=True)
            self.client.disconnect()
            await asyncio.to_thread(self.client.loop_stop)
