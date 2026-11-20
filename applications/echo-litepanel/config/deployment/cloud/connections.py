import base64
import asyncio
import importlib.util
import json
import math
import queue
import secrets
import socket
import threading
import time
from collections import deque
from mqtt_camera import CameraFrames
import capabilities
import wire_protocol as wire


KINDS = {"simulation", "wifi", "serial", "usb", "ble", "mqtt"}
BLE_SCAN_DEVICES = {}
BLE_SCAN_LOCK = threading.Lock()
BLE_NOTIFY_UUID = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'
BLE_WRITE_UUID = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
FIELDS = {"battery", "voltage", "temperature", "humidity", "channels", "pwm", "color", "light", "speed", "gimbal_pan", "gimbal_tilt", "direction", "rate", "settings", "breathe_hz", "audio_playing", "audio_volume", "voice_listen", "voice_talk", "voice_rx_frames", "voice_tx_frames", "voice_mic_peak", "wifi_rssi", "rssi", "wifi_signal_age_ms"}


def dependencies():
    return {"serial": importlib.util.find_spec("serial") is not None,
            "ble": importlib.util.find_spec("bleak") is not None,
            "mqtt": importlib.util.find_spec("paho") is not None}


def ports():
    try:
        from serial.tools import list_ports
    except ImportError:
        raise ValueError("请先运行安装连接依赖.bat，安装 pyserial")
    return [{"port": item.device, "name": item.description} for item in list_ports.comports()]


def scan_ble():
    try:
        from bleak import BleakScanner
    except ImportError:
        raise ValueError("请先运行安装连接依赖.bat，安装 bleak")

    async def discover():
        devices = await BleakScanner.discover(timeout=5, return_adv=True)
        with BLE_SCAN_LOCK:
            for device, _ in devices.values():
                BLE_SCAN_DEVICES[device.address.casefold()] = (device, time.monotonic())
        results = {item.address.casefold(): {"address": item.address,
                   "name": advertisement.local_name or item.name or "未命名设备",
                   "rssi": advertisement.rssi}
                   for item, advertisement in devices.values()}
        # Connected peripherals may stop advertising; keep them selectable by address.
        with MANAGER.operation:
            sessions = [(entry['session'], entry['name']) for entry in MANAGER.devices.values()
                        if entry['kind'] == 'ble' and entry['session']]
            if MANAGER.kind == 'ble' and MANAGER.session:
                sessions.append((MANAGER.session, MANAGER.session.config.get('name')))
            for session, name in sessions:
                if not session.connected:
                    continue
                address = session.config['address']
                results.setdefault(address.casefold(), {"address": address,
                                   "name": name or address, "rssi": None})
        return sorted(results.values(),
                      key=lambda item: item['rssi'] if item['rssi'] is not None else -999,
                      reverse=True)

    try:
        return asyncio.run(discover())
    except Exception as error:
        raise ValueError('BLE 扫描失败：' + str(error) + '。请确认运行 LitePanel 后台的电脑已开启蓝牙，并允许使用蓝牙。'
                         '若后台运行在云服务器，请改为本机运行后扫描。') from error


def validate(config):
    if isinstance(config, dict) and config.get('kind') == 'mqtt4g':
        config = dict(config, kind='mqtt', network='4g')
    if not isinstance(config, dict) or config.get("kind") not in KINDS:
        raise ValueError("请选择有效的连接方式")
    result = dict(config)
    kind = result["kind"]
    if kind in ("wifi", "mqtt"):
        host = result.get("host", "").strip()
        port = int(result.get("port", 8883 if kind == "mqtt" else 9000))
        if not host or "://" in host or not 1 <= port <= 65535:
            raise ValueError("请输入主机名或 IP 及有效端口，不包含协议前缀")
        result.update(host=host, port=port)
    if kind in ("serial", "usb"):
        if not isinstance(result.get("port"), str) or not result["port"].strip():
            raise ValueError("请选择 COM 串口；USB 当前支持 CDC / USB 转串口")
        result["baud"] = int(result.get("baud", 115200))
        if not 300 <= result["baud"] <= 4000000:
            raise ValueError("波特率无效")
    if kind == "ble":
        if not result.get('notify_uuid'):
            result['notify_uuid'] = BLE_NOTIFY_UUID
        if not result.get('write_uuid'):
            result['write_uuid'] = BLE_WRITE_UUID
        for key in ("address", "notify_uuid", "write_uuid"):
            if not isinstance(result.get(key), str) or not result[key].strip():
                raise ValueError("请先扫描并选择蓝牙设备")
    if kind == "mqtt":
        for key in ("up_topic", "down_topic"):
            topic = result.get(key, "")
            if not isinstance(topic, str) or not topic or any(character in topic for character in ("#", "+", "\x00")):
                raise ValueError("请输入具体设备的上下行主题，不能包含通配符")
        if result["up_topic"] == result["down_topic"]:
            raise ValueError("上行和下行主题必须不同")
    return result


class Session:
    def __init__(self, config):
        self.config = config
        self.identifier = str(time.time_ns())
        self.camera = CameraFrames()
        self.sample_clock = None
        self.sample_clock_last = None
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.connected = False
        self.error = ""
        self.buffer = bytearray()
        self.decoder = wire.Decoder()
        self.values = {}
        self.received = 0
        self.packet_stats = None
        self.last_received = None
        self.audio_in = deque(maxlen=8)
        self.audio_out = deque(maxlen=8)
        self.frames = deque(maxlen=20000)
        self.outgoing = queue.Queue(maxsize=64)
        self.resource = None
        self.thread = None
        self.seq = 0
        self.pending = {}
        self.command_results = deque(maxlen=64)
        self.last_command = None
        self.dropped = 0
        self.motion_deadline = None
        self.protocol_outgoing = deque(maxlen=8)

    def request_capabilities(self):
        with self.lock:
            self.protocol_outgoing.append(wire.encode({'v':1,'type':'capabilities_request','payload':{}}))

    def feed(self, data, sample_time=None):
        errors = self.decoder.errors
        for message in self.decoder.feed(data):
            try:
                if not isinstance(message, dict) or message.get("v") != 1:
                    raise ValueError("协议版本无效")
                if message.get("type") == "telemetry_batch":
                    self._feed_batch(message)
                    continue
                payload = message.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError("payload 必须是对象")
                with self.lock:
                    if message.get('type') == 'capabilities':
                        declaration = capabilities.declaration(payload)
                        self.values['capabilities'] = declaration
                        sequence = message.get('seq')
                        if type(sequence) is int and 0 <= sequence <= 4294967295:
                            ack = {'v': 1, 'type': 'capabilities_ack', 'seq': sequence, 'payload': {'ok': True}}
                            self.protocol_outgoing.append(wire.encode(ack))
                    elif message.get("type") == "ack":
                        sequence = message.get("seq")
                        if sequence in self.pending:
                            command = self.pending.pop(sequence)
                            command.update(status="confirmed" if payload.get("ok") is True else "rejected", error=str(payload.get("error", "")))
                            if self.last_command and self.last_command["seq"] == sequence:
                                self.last_command = command
                    elif message.get("type") == "audio":
                        validate_audio(payload)
                        if self.config["kind"] in ("wifi", "mqtt"):
                            self.audio_in.append((time.monotonic(), payload))
                    elif message.get("type") in ("telemetry", "status"):
                        values = {key: value for key, value in payload.items() if key in FIELDS}
                        if 'capabilities' in payload:
                            values['capabilities'] = capabilities.normalize(payload['capabilities'])
                        if 'signals' in payload:
                            values['signals'] = capabilities.measurements(payload['signals'])
                        if 'charging' in payload:
                            if type(payload['charging']) is not bool:
                                raise ValueError('charging must be boolean')
                            values['charging'] = payload['charging']
                        if 'data_source' in payload:
                            if payload['data_source'] not in ('mock', 'real'):
                                raise ValueError('invalid data_source')
                            values['data_source'] = payload['data_source']
                        if 'camera_mock' in payload:
                            if type(payload['camera_mock']) is not bool:
                                raise ValueError('invalid camera_mock')
                            values['camera_mock'] = payload['camera_mock']
                        for key, value in values.items():
                            if key == "settings":
                                from alarms import validate_settings
                                validate_settings(value)
                            elif key == "channels":
                                if not isinstance(value, list) or len(value) != 3 or not all(type(item) in (int, float) and math.isfinite(item) for item in value):
                                    raise ValueError("channels 需要三个有限数值")
                            elif key in ("breathe_hz", "audio_volume"):
                                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
                                    raise ValueError("breathe_hz must be between 0 and 100")
                            elif key in ("battery", "voltage", "temperature", "humidity", "pwm", "speed", "gimbal_pan", "gimbal_tilt", "rate", "voice_rx_frames", "voice_tx_frames", "voice_mic_peak", "wifi_rssi", "rssi", "wifi_signal_age_ms"):
                                if type(value) not in (int, float) or not math.isfinite(value):
                                    raise ValueError("数值字段无效")
                            elif key in ("light", "audio_playing", "voice_listen", "voice_talk") and not isinstance(value, bool):
                                raise ValueError("light 需要布尔值")
                            elif key == "direction" and value not in ("stop", "forward", "backward", "left", "right"):
                                raise ValueError("direction 无效")
                            elif key == "color":
                                if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
                                    raise ValueError("color 无效")
                                int(value[1:], 16)
                        if not values:
                            raise ValueError("没有可识别的数据字段")
                        self.values.update(values)
                        if message["type"] == "status":
                            self.error = ""
                            continue
                        seq = message.get("sample_seq")
                        if type(seq) is int and 0 <= seq <= 0xffffffff:
                            stats = self.packet_stats
                            delta = (seq - stats["last"]) & 0xffffffff if stats else None
                            if stats is None or delta >= 0x80000000:
                                self.packet_stats = {"last": seq, "received": 1, "expected": 1}
                            elif delta:
                                stats.update(last=seq, received=stats["received"] + 1, expected=stats["expected"] + delta)
                        self.received += 1
                        self.last_received = time.time()
                        if len(self.frames) == self.frames.maxlen:
                            self.dropped += 1
                        frame = dict(self.values, time=self.last_received if sample_time is None else sample_time, frame_id=self.received)
                        for name in ("sample_seq", "sample_time_us"):
                            if type(message.get(name)) in (int, float):
                                frame[name] = message[name]
                        self.frames.append(frame)
                    else:
                        raise ValueError("不支持的消息类型")
                    self.error = ""
            except (ValueError, TypeError, UnicodeError):
                self.error = "收到无效协议帧，请检查 JSON 行协议"
        if self.decoder.errors != errors:
            self.error = "Binary frame rejected (header/length/CRC); stream resynchronized"

    def send(self, key, value):
        with self.lock:
            if not self.connected or self.stop.is_set():
                raise ValueError("连接已断开")
            self.seq += 1
            command = {"seq": self.seq, "key": key, "status": "sent", "sent_at": time.time()}
            message = {"v": 1, "type": "set" if key == "set" else "command", "seq": self.seq, "payload": value if key == "set" else {"key": key, "value": value}}
            try:
                self.outgoing.put_nowait((wire.encode(message), time.monotonic(), key == "direction" and value != "stop"))
            except queue.Full:
                raise ValueError("发送队列繁忙，请稍后重试")
            if key == 'voice_talk':
                self.audio_out.clear()
            if key == 'voice_listen' and value is False:
                self.audio_in.clear()
            self.pending[self.seq] = command
            self.command_results.append(command)
            self.last_command = command
            if key == "direction":
                self.motion_deadline = None if value == "stop" else time.monotonic() + .7
            return command.copy()

    def send_audio(self, payload):
        validate_audio(payload)
        if self.config['kind'] not in ('wifi', 'mqtt') or not self.connected:
            raise ValueError('实时对讲请连接 Wi-Fi 设备')
        message = wire.encode(dict(v=1, type='audio', payload=payload))
        with self.lock:
            self.audio_out.append((time.monotonic(), message))

    def receive_audio(self):
        with self.lock:
            frames = [payload for created, payload in self.audio_in if time.monotonic() - created < .25]
            self.audio_in.clear()
            return frames

    def next_message(self):
        with self.lock:
            if self.protocol_outgoing:
                return self.protocol_outgoing.popleft()
            if self.motion_deadline and time.monotonic() >= self.motion_deadline:
                self.send("direction", "stop")
        while True:
            try:
                message, created, motion = self.outgoing.get_nowait()
            except queue.Empty:
                with self.lock:
                    while self.audio_out:
                        created, message = self.audio_out.popleft()
                        if time.monotonic() - created < .25:
                            return message
                raise
            if not motion or time.monotonic() - created < .5:
                return message

    def snapshot(self):
        with self.lock:
            for sequence, command in list(self.pending.items()):
                if time.time() - command["sent_at"] > 3:
                    command["status"] = "timeout"
                # A delayed WAN ACK still matters; retain a bounded window for matching.
                if time.time() - command["sent_at"] > 60:
                    del self.pending[sequence]
            return {"kind": self.config["kind"], "connected": self.connected, "error": self.error,
                    "session_id": self.identifier,
                    "properties_ready": 'capabilities' in self.values,
                    "ble_write_size": getattr(self, "ble_write_size", None),
                    "packet_rate": (100 * self.packet_stats["received"] / self.packet_stats["expected"]) if self.packet_stats else None,
                    "packet_stats": dict(self.packet_stats) if self.packet_stats else None,
                    "wire_errors": self.decoder.errors,
                    "received": self.received, "last_received": self.last_received,
                    "stale": self.last_received is None or time.time() - self.last_received > 5,
                    "values": self.values.copy(), "last_command": self.last_command,
                    "dropped": self.dropped, "command_results": [dict(item) for item in self.command_results]}

    def run(self):
        try:
            kind = self.config["kind"]
            if kind == "ble":
                asyncio.run(self.run_ble())
            elif kind == "mqtt":
                self.run_mqtt()
            else:
                self.run_stream()
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self.error = f"连接失败或已断开：{type(error).__name__}：{error}"
        finally:
            self.connected = False
            self.ready.set()
            if self.resource:
                try:
                    self.resource.close()
                except Exception:
                    pass

    def run_stream(self):
        if self.config["kind"] == "wifi":
            self.resource = socket.create_connection((self.config["host"], self.config["port"]), timeout=5)
            self.resource.settimeout(.02)
            receive = lambda: self.resource.recv(4096)
            send = self.resource.sendall
        else:
            try:
                import serial
            except ImportError:
                self.error = "缺少 pyserial，请运行安装连接依赖.bat"
                return
            self.resource = serial.Serial(self.config["port"], self.config["baud"], timeout=.1, write_timeout=2)
            receive = lambda: self.resource.read(self.resource.in_waiting or 1)
            send = self.resource.write
        self.connected = True
        self.request_capabilities()
        self.ready.set()
        while not self.stop.is_set():
            for _ in range(16):
                try:
                    send(self.next_message())
                except queue.Empty:
                    break
            try:
                data = receive()
                if not data and self.config["kind"] == "wifi":
                    raise ConnectionError("设备关闭了连接")
                if data:
                    self.feed(data)
            except socket.timeout:
                pass

    async def run_ble(self):
        self.ble_loop = asyncio.get_running_loop()
        self.ble_task = asyncio.current_task()
        try:
            from bleak import BleakClient
        except ImportError:
            self.error = "缺少 bleak，请运行安装连接依赖.bat"
            return
        address = self.config["address"]
        with BLE_SCAN_LOCK:
            cached = BLE_SCAN_DEVICES.get(address.casefold())
        target = cached[0] if cached and time.monotonic() - cached[1] < 60 else address
        if self.config.get('_ble_rediscover'):
            from bleak import BleakScanner
            target = await BleakScanner.find_device_by_address(address, timeout=5)
            if target is None:
                raise ValueError("未发现该地址的设备广播，请确认设备已开机且未连接其他手机或程序")
        # Reuse the discovered device to avoid Bleak's implicit second scan.
        async with BleakClient(target, timeout=12) as client:
            characteristic = client.services.get_characteristic(self.config["write_uuid"])
            if characteristic is None:
                raise ValueError("设备不支持 LitePanel 蓝牙协议，请选择正确设备；其他固件可在高级设置填写 UUID")
            await client.start_notify(self.config["notify_uuid"], lambda sender, data: self.feed(data))
            response = "write" in characteristic.properties
            self.connected = True
            self.request_capabilities()
            self.ready.set()
            while not self.stop.is_set() and client.is_connected:
                try:
                    message = self.next_message()
                    chunk_size = min(180, max(20, getattr(client, "mtu_size", 23) - 3)) if response else min(180, characteristic.max_write_without_response_size)
                    self.ble_write_size = chunk_size
                    for offset in range(0, len(message), chunk_size):
                        try:
                            await asyncio.wait_for(client.write_gatt_char(characteristic, message[offset:offset + chunk_size], response=response), timeout=15)
                        except asyncio.TimeoutError as error:
                            raise TimeoutError("BLE 写入 15 秒未完成，连接已关闭以清除未完成的命令分片；请重新连接，并检查设备是否仍被手机或其他程序占用") from error
                except queue.Empty:
                    await asyncio.sleep(.03)

            if not self.stop.is_set():
                self.error = "BLE 链路意外断开。请查看设备日志中的 Disconnected reason；设备可能重启、超出距离，或切换了连接端。"

    def feed_mqtt(self, packet):
        self.feed(packet)

    def _feed_batch(self, value):
        if isinstance(value, dict) and value.get("type") == "telemetry_batch":
            samples = value.get("samples")
            if value.get("v") != 1 or not isinstance(samples, list) or not 1 <= len(samples) <= 32:
                raise ValueError("批量采样格式无效")
            previous = None
            for sample in samples:
                if not isinstance(sample, dict) or sample.get("type") != "telemetry" or sample.get("v") != 1:
                    raise ValueError("批量采样帧无效")
                stamp = sample.get("sample_time_us")
                if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 or (previous is not None and stamp <= previous):
                    raise ValueError("采样时间无效")
                previous = stamp
            arrival = time.time()
            end = samples[-1]["sample_time_us"]
            if end - samples[0]["sample_time_us"] > 5_000_000:
                raise ValueError("批量采样时间跨度过大")
            if self.sample_clock is None or (self.sample_clock_last is not None and samples[0]["sample_time_us"] <= self.sample_clock_last):
                self.sample_clock = arrival - end / 1_000_000
            self.sample_clock_last = end
            for sample in samples:
                stamp = self.sample_clock + sample["sample_time_us"] / 1_000_000
                self.feed(wire.encode(sample), sample_time=stamp)
        else:
            self.feed(wire.encode(value))

    def run_mqtt(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.error = "缺少 paho-mqtt，请运行安装连接依赖.bat"
            return
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, reconnect_on_failure=False)
        client.connect_timeout = 5
        if self.config.get("username"):
            client.username_pw_set(self.config["username"], self.config.get("password", ""))
        if self.config.get("tls", True):
            client.tls_set()

        def on_connect(current, userdata, flags, reason, properties):
            if reason.is_failure:
                self.error = "MQTT 认证或连接被拒绝"
                self.ready.set()
            else:
                current.subscribe([(self.config["up_topic"], 1), (self.config["up_topic"] + "/camera", 0)])

        def on_subscribe(current, userdata, message_id, reasons, properties):
            if any(reason.is_failure for reason in reasons):
                self.error = "MQTT 上行主题订阅被拒绝"
            else:
                self.connected = True
                self.request_capabilities()
            self.ready.set()

        def on_message(current, userdata, message):
            if not message.retain:
                if message.topic == self.config["up_topic"] + "/camera":
                    with self.lock:
                        self.camera.feed(message.payload)
                    return
                try:
                    self.feed_mqtt(message.payload)
                except (ValueError, UnicodeError):
                    self.error = "MQTT 消息不是有效的 JSON 对象或超过长度限制"

        def on_disconnect(current, userdata, flags, reason, properties):
            self.connected = False
            if not self.stop.is_set():
                self.error = "MQTT 连接已断开"
                self.stop.set()

        client.on_connect, client.on_subscribe = on_connect, on_subscribe
        client.on_message, client.on_disconnect = on_message, on_disconnect
        try:
            client.connect(self.config["host"], self.config["port"], keepalive=30)
            client.loop_start()
            while not self.stop.wait(.03):
                # Drain a bounded burst so PCM frames do not compete for one
                # 30ms slot with control heartbeats and capability ACKs.
                for _ in range(8):
                    try:
                        message = self.next_message()
                    except queue.Empty:
                        break
                    result = client.publish(self.config["down_topic"], message, qos=0, retain=False)
                    if result.rc != mqtt.MQTT_ERR_SUCCESS:
                        raise ConnectionError("MQTT 发送失败")
        finally:
            client.disconnect()
            client.loop_stop()


class ConnectionManager:
    def __init__(self):
        self.session = None
        self.kind = "simulation"
        self.operation = threading.RLock()
        self.devices = {}
        self.active_id = None

    def add_device(self, config):
        """Open a new independent link without closing existing devices."""
        config = validate(config)
        with self.operation:
            identity = {k: v for k, v in config.items() if k not in ('password', 'name')}
            for identifier, entry in self.devices.items():
                if entry['identity'] == identity:
                    self.select_device(identifier)
                    if self.kind != 'simulation' and not self.session.connected:
                        self.connect(config)
                        entry['session'] = self.session
                    return identifier
            candidate = ConnectionManager()
            candidate.connect(config)
            identifier = secrets.token_hex(8)
            self.devices[identifier] = {'kind': candidate.kind, 'session': candidate.session,
                                       'identity': identity, 'name': str(config.get('name') or config.get('up_topic') or config.get('host') or config.get('address') or config.get('port') or config['kind'])[:100]}
            self.select_device(identifier)
            return identifier

    def select_device(self, identifier):
        with self.operation:
            if identifier not in self.devices:
                raise ValueError('设备不存在，请刷新设备列表')
            entry = self.devices[identifier]
            self.kind, self.session, self.active_id = entry['kind'], entry['session'], identifier
            # Old background display frames must never enter a new acquisition.
            if self.session:
                with self.session.lock:
                    self.session.frames.clear()

    def device_list(self):
        with self.operation:
            return [dict(id=identifier, name=entry['name'], active=identifier == self.active_id,
                         connection=entry['session'].snapshot() if entry['session'] else
                         {'kind': 'simulation', 'connected': True, 'values': {}, 'stale': False})
                    for identifier, entry in self.devices.items()]

    def reconnect_device(self, identifier):
        with self.operation:
            if identifier not in self.devices:
                raise ValueError('Device no longer exists')
            entry = self.devices[identifier]
            previous = entry['session']
            if previous is None or previous.connected:
                return
            config = dict(previous.config)
            if config.get('kind') == 'ble':
                config['_ble_rediscover'] = True
            previous.stop.set()
            loop, task = getattr(previous, 'ble_loop', None), getattr(previous, 'ble_task', None)
            if loop and task and not loop.is_closed():
                loop.call_soon_threadsafe(task.cancel)
            if previous.thread:
                previous.thread.join(timeout=6)
                if previous.thread.is_alive():
                    raise ValueError('旧连接仍在释放，请稍后重试；不会重复建立同一设备的连接')
            candidate = ConnectionManager()
            candidate.connect(config)
            entry['session'] = candidate.session
            if self.active_id == identifier:
                self.session = candidate.session

    def rename_device(self, identifier, name):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100 or any(ord(c) < 32 for c in name):
            raise ValueError('设备名称需为 1～100 个字符，不能包含控制字符')
        with self.operation:
            if identifier not in self.devices:
                raise ValueError('设备不存在，请刷新设备列表')
            self.devices[identifier]['name'] = name.strip()

    def remove_device(self, identifier):
        with self.operation:
            if identifier not in self.devices:
                raise ValueError('设备不存在')
            entry = self.devices.pop(identifier)
            if entry['session']:
                entry['session'].stop.set()
                entry['session'].connected = False
            if identifier == self.active_id:
                self.active_id = None
                self.session = None
                self.kind = entry['kind']

    def disconnect_all(self):
        for identifier in list(self.devices):
            self.remove_device(identifier)
        self.disconnect()

    def connect(self, config):
        config = validate(config)
        with self.operation:
            self.disconnect()
            self.kind = config["kind"]
            if self.kind == "simulation":
                return
            session = Session(config)
            self.session = session
            session.thread = threading.Thread(target=session.run, daemon=True)
            session.thread.start()
            if not session.ready.wait(25 if config.get('_ble_rediscover') else 18) or not session.connected:
                session.stop.set()
                raise ValueError(session.error or "连接超时，请检查设备和连接参数")

    def disconnect(self):
        with self.operation:
            if self.session:
                self.session.stop.set()
                self.session.connected = False
                if self.session.thread:
                    self.session.thread.join(timeout=2)

    def snapshot(self):
        session = self.session
        if self.kind != "simulation":
            if session:
                return session.snapshot()
            return {"kind": self.kind, "connected": False, "error": "正在连接", "received": 0,
                    "last_received": None, "stale": True, "values": {}, "last_command": None, "dropped": 0}
        return {"kind": "simulation", "error": "", "received": 0, "last_received": None,
                "stale": False, "last_command": None, "dropped": 0}


MANAGER = ConnectionManager()

def validate_audio(payload):
    if not isinstance(payload, dict) or payload.get('codec') != 'pcm_s16le' or type(payload.get('sample_rate')) is not int or payload['sample_rate'] != 16000:
        raise ValueError('音频格式必须为 PCM 16kHz 单声道')
    data = payload.get('data')
    if not isinstance(data, str) or not 0 < len(data) <= 1368:
        raise ValueError('音频帧长度无效')
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError('音频编码无效') from error
    if not 0 < len(raw) <= 1024 or len(raw) % 2:
        raise ValueError('音频 PCM 帧长度无效')
    return raw
