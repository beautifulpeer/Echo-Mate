"""LitePanel binary protocol v1. JSON is never used on the device wire."""
import math
import binascii
import struct
from pathlib import Path

KEYS = __import__('json').loads(Path(__file__).with_name('wire_schema.json').read_text(encoding='utf-8'))['keys']
KEY_IDS = {key: index + 1 for index, key in enumerate(KEYS)}
TYPES = {'telemetry': (1, 1), 'audio': (1, 2), 'telemetry_batch': (1, 3),
         'status': (2, 1), 'capabilities': (2, 2), 'ack': (2, 3),
         'command': (3, 1), 'set': (3, 2), 'capabilities_request': (3, 3), 'capabilities_ack': (3, 4)}
NAMES = {value: key for key, value in TYPES.items()}
MAX_PAYLOAD = 65535

def crc16(data):
    return binascii.crc_hqx(data, 0xffff)

def _string(value):
    data = value.encode('utf-8')
    if b'\0' in data or len(data) > 65535:
        raise ValueError('Invalid binary string')
    return struct.pack('<H', len(data)) + data

def _value(value, depth=0):
    if depth > 16:
        raise ValueError('Binary nesting limit')
    if value is None: return b'\0'
    if value is False: return b'\1'
    if value is True: return b'\2'
    if type(value) in (int, float):
        if not math.isfinite(value): raise ValueError('Non-finite value')
        if int(value) == value and -2147483648 <= value <= 2147483647:
            return b'\3' + struct.pack('<i', int(value))
        if int(value) == value and 0 <= value <= 0xffffffff:
            return b'\4' + struct.pack('<I', int(value))
        return b'\5' + struct.pack('<d', value)
    if isinstance(value, str): return b'\6' + _string(value)
    if isinstance(value, list):
        if len(value) > 4096: raise ValueError('Too many items')
        return b'\7' + struct.pack('<H', len(value)) + b''.join(_value(v, depth + 1) for v in value)
    if isinstance(value, dict):
        if len(value) > 4096: raise ValueError('Too many fields')
        return b'\10' + struct.pack('<H', len(value)) + b''.join(
            (bytes([KEY_IDS[k]]) if k in KEY_IDS else b'\0' + _string(k)) + _value(v, depth + 1)
            for k, v in value.items())
    raise ValueError('Unsupported binary value')

class Reader:
    def __init__(self, data): self.data, self.pos = data, 0
    def take(self, size):
        if self.pos + size > len(self.data): raise ValueError('Truncated binary payload')
        data = self.data[self.pos:self.pos + size]; self.pos += size
        return data
    def number(self, fmt): return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]
    def string(self):
        data = self.take(self.number('<H'))
        if b'\0' in data: raise ValueError('NUL string')
        return data.decode('utf-8')
    def value(self, depth=0):
        if depth > 16: raise ValueError('Binary nesting limit')
        tag = self.number('<B')
        if tag < 3: return (None, False, True)[tag]
        if tag in (3, 4, 5):
            result = self.number({3: '<i', 4: '<I', 5: '<d'}[tag])
            if not math.isfinite(result): raise ValueError('Non-finite number')
            return result
        if tag == 6: return self.string()
        if tag not in (7, 8): raise ValueError('Unknown value tag')
        count = self.number('<H')
        if count > 4096: raise ValueError('Too many items')
        if tag == 7: return [self.value(depth + 1) for _ in range(count)]
        result = {}
        for _ in range(count):
            key = self.number('<B')
            if key > len(KEYS): raise ValueError('Unknown field ID')
            key = KEYS[key - 1] if key else self.string()
            if key in result or key in ('__proto__', 'constructor', 'prototype'): raise ValueError('Duplicate or unsafe key')
            result[key] = self.value(depth + 1)
        return result

def encode(message):
    if message.get('v') != 1: raise ValueError('Protocol version')
    kind, opcode = TYPES[message['type']]
    payload = bytes([opcode]) + _value({k: v for k, v in message.items() if k not in ('v', 'type')})
    if len(payload) > MAX_PAYLOAD: raise ValueError('Frame too long')
    frame = b'\xa5\x5a' + bytes([1, kind]) + struct.pack('<I', len(payload)) + payload
    return frame + struct.pack('<H', crc16(frame))

def decode(frame):
    if len(frame) < 12 or frame[:2] != b'\xa5\x5a' or frame[2] != 1: raise ValueError('Invalid binary header')
    length = struct.unpack_from('<I', frame, 4)[0]
    if length > MAX_PAYLOAD or len(frame) != length + 10: raise ValueError('Invalid frame length')
    if crc16(frame[:-2]) != struct.unpack_from('<H', frame, len(frame) - 2)[0]: raise ValueError('CRC mismatch')
    name = NAMES.get((frame[3], frame[8]))
    if name is None: raise ValueError('Unknown packet kind/opcode')
    reader = Reader(frame[9:-2]); body = reader.value()
    if not isinstance(body, dict) or reader.pos != len(reader.data) or 'v' in body or 'type' in body: raise ValueError('Invalid message body')
    return dict(v=1, type=name, **body)

class Decoder:
    def __init__(self): self.buffer, self.errors = bytearray(), 0
    def feed(self, data):
        self.buffer.extend(data); messages = []
        while len(self.buffer) >= 2:
            if self.buffer[:2] != b'\xa5\x5a':
                del self.buffer[0]; self.errors += 1; continue
            if len(self.buffer) < 8: break
            size = struct.unpack_from('<I', self.buffer, 4)[0]
            if self.buffer[2] != 1 or self.buffer[3] not in (1, 2, 3) or size < 2 or size > MAX_PAYLOAD:
                del self.buffer[0]; self.errors += 1; continue
            if len(self.buffer) < size + 10:
                # A damaged length must not hide a later complete, CRC-valid frame.
                candidate = self.buffer.find(b'\xa5\x5a', 1)
                recovered = False
                while candidate >= 0 and len(self.buffer) - candidate >= 12:
                    length = struct.unpack_from('<I', self.buffer, candidate + 4)[0]
                    if 2 <= length <= MAX_PAYLOAD and candidate + length + 10 <= len(self.buffer):
                        try: decode(bytes(self.buffer[candidate:candidate + length + 10]))
                        except (ValueError, UnicodeError): pass
                        else:
                            del self.buffer[:candidate]; self.errors += 1; recovered = True; break
                    candidate = self.buffer.find(b'\xa5\x5a', candidate + 1)
                if recovered: continue
                break
            try: message = decode(bytes(self.buffer[:size + 10]))
            except (ValueError, UnicodeError):
                del self.buffer[0]; self.errors += 1; continue
            del self.buffer[:size + 10]; messages.append(message)
        return messages
