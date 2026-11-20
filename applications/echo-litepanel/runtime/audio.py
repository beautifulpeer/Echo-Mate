"""ALSA PCM subprocesses. Hardware errors are surfaced instead of mocked."""
import array
import asyncio
import base64
import math
import sys
import time


class Audio:
    def __init__(self, device='plughw:0,0'):
        self.device = device
        self.volume = 30
        self.listen = self.talk = self.playing = False
        self.rx = self.tx = self.peak = 0
        self.deadline = 0
        self.player = self.recorder = None
        self.melody_task = None
        self.speaker_task = None
        self.speaker_queue = asyncio.Queue(maxsize=8)
        self.error = ''

    async def _process(self, program):
        args = [program, '-q', '-D', self.device, '-t', 'raw', '-f', 'S16_LE',
                '-r', '16000', '-c', '1']
        if program == 'aplay':
            args += ['--buffer-time=128000', '--period-time=32000']
        process = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE if program == 'aplay' else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE if program == 'arecord' else asyncio.subprocess.DEVNULL)
        await asyncio.sleep(.05)
        if process.returncode is not None:
            raise ValueError('audio_device_unavailable')
        return process

    async def _kill(self, process):
        if process and process.returncode is None:
            try:
                if process.stdin:
                    process.stdin.close()
                process.terminate()
                await asyncio.wait_for(process.wait(), .08)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass

    async def _player(self):
        if not self.player or self.player.returncode is not None:
            self.player = await self._process('aplay')

    async def command(self, key, value):
        if key == 'audio_volume':
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError('invalid_audio_volume')
            self.volume = value
            return
        if type(value) is not bool:
            raise ValueError('expected_boolean')
        if key == 'audio_playing':
            await self.stop()
            if value:
                await self._player()
                self.playing = True
                self.melody_task = asyncio.create_task(self._melody())
            return
        if key not in ('voice_talk', 'voice_listen'):
            raise ValueError('unsupported_audio_command')
        if self.playing:
            await self.stop()
        if key == 'voice_talk':
            if value:
                await self._player()
            self.talk = value
            if value and (not self.speaker_task or self.speaker_task.done()):
                self.speaker_task = asyncio.create_task(self._speaker())
            if not value:
                await self._stop_speaker()
                await self._kill(self.player)
                self.player = None
        else:
            if value and (not self.recorder or self.recorder.returncode is not None):
                self.recorder = await self._process('arecord')
            self.listen = value
            if not value:
                await self._kill(self.recorder)
                self.recorder = None
        self.deadline = time.monotonic() + 2.5

    def _scale(self, pcm):
        if self.volume == 100:
            return pcm
        if self.volume == 0:
            return bytes(len(pcm))
        values = array.array('h')
        values.frombytes(pcm)
        if sys.byteorder != 'little':
            values.byteswap()
        gain = self.volume / 100
        values = array.array('h', (int(value * gain) for value in values))
        if sys.byteorder != 'little':
            values.byteswap()
        return values.tobytes()

    async def receive(self, payload):
        if not self.talk or not self.player or self.player.returncode is not None:
            raise ValueError('voice_talk_not_active')
        if payload.get('codec') != 'pcm_s16le' or payload.get('sample_rate') != 16000:
            raise ValueError('unsupported_audio_format')
        pcm = base64.b64decode(payload.get('data', ''), validate=True)
        if not pcm or len(pcm) > 1024 or len(pcm) % 2:
            raise ValueError('invalid_audio_length')
        # Never wait for ALSA from the control reader: a slow pipe used to
        # delay movement/voice heartbeats and close the entire MQTT session.
        if self.speaker_queue.full():
            self.speaker_queue.get_nowait()
        self.speaker_queue.put_nowait(pcm)
        self.rx += 1

    async def _stop_speaker(self):
        if self.speaker_task:
            self.speaker_task.cancel()
            await asyncio.gather(self.speaker_task, return_exceptions=True)
            self.speaker_task = None
        while not self.speaker_queue.empty():
            self.speaker_queue.get_nowait()

    async def _speaker(self):
        player = self.player
        # Three PCM frames absorb short HTTP/MQTT bursts without accumulating
        # seconds of old speech. Silence keeps ALSA running between bursts.
        await asyncio.sleep(.096)
        deadline = time.monotonic()
        try:
            while self.talk and player and player.returncode is None:
                try:
                    pcm = self.speaker_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pcm = bytes(1024)
                player.stdin.write(self._scale(pcm))
                await asyncio.wait_for(player.stdin.drain(), .3)
                deadline = max(deadline + len(pcm) / 32000, time.monotonic())
                await asyncio.sleep(max(0, deadline - time.monotonic()))
        except (OSError, asyncio.TimeoutError) as error:
            self.error = str(error) or 'speaker_write_timeout'
            self.talk = False

    async def capture(self):
        recorder = self.recorder
        if not recorder or recorder.returncode is not None:
            await asyncio.sleep(.02)
            return None
        try:
            pcm = await asyncio.wait_for(recorder.stdout.readexactly(1024), .2)
        except asyncio.TimeoutError:
            return None
        except asyncio.IncompleteReadError:
            # A concurrent listen-off command intentionally terminates arecord.
            # Do not tear down the speaker if talk has just been enabled.
            if self.recorder is recorder:
                self.recorder = None
                self.listen = False
                self.error = 'microphone_stream_ended'
            return None
        if not self.listen or self.talk:
            return None
        values = array.array('h')
        values.frombytes(pcm)
        if sys.byteorder != 'little':
            values.byteswap()
        self.peak = max(abs(v) for v in values)
        self.tx += 1
        return {'codec': 'pcm_s16le', 'sample_rate': 16000,
                'data': base64.b64encode(pcm).decode('ascii')}

    async def _melody(self):
        try:
            phase = 0
            while self.playing:
                freq = (262, 330, 392, 523)[(phase // 16000) % 4]
                samples = array.array('h', (int(6000 * math.sin(2 * math.pi * freq * (phase + n) / 16000))
                                            for n in range(512)))
                if sys.byteorder != 'little':
                    samples.byteswap()
                self.player.stdin.write(self._scale(samples.tobytes()))
                await asyncio.wait_for(self.player.stdin.drain(), .2)
                phase += 512
                await asyncio.sleep(.032)
        except (OSError, asyncio.TimeoutError) as error:
            self.error = str(error)
        finally:
            self.playing = False

    async def stop(self):
        self.listen = self.talk = self.playing = False
        await self._stop_speaker()
        if self.melody_task:
            self.melody_task.cancel()
            await asyncio.gather(self.melody_task, return_exceptions=True)
            self.melody_task = None
        await self._kill(self.player)
        await self._kill(self.recorder)
        self.player = self.recorder = None

    async def tick(self):
        if (self.listen or self.talk) and time.monotonic() >= self.deadline:
            await self.stop()

    def status(self):
        return dict(audio_volume=self.volume, audio_playing=self.playing,
                    voice_listen=self.listen, voice_talk=self.talk,
                    voice_rx_frames=self.rx, voice_tx_frames=self.tx, voice_mic_peak=self.peak)
