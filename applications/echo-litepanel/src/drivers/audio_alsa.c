#include "echo/audio.h"
#include "echo/platform.h"
#include <errno.h>
#include <math.h>
#include <string.h>

static void close_pcm(snd_pcm_t **pcm) {
    if (*pcm) { snd_pcm_drop(*pcm); snd_pcm_close(*pcm); *pcm = NULL; }
}
static int open_pcm(echo_audio_t *audio, snd_pcm_t **pcm, snd_pcm_stream_t stream) {
    if (*pcm) return 0;
    if (!audio->enabled || snd_pcm_open(pcm, audio->device, stream, SND_PCM_NONBLOCK) < 0) return -1;
    int rc = snd_pcm_set_params(*pcm, SND_PCM_FORMAT_S16_LE, SND_PCM_ACCESS_RW_INTERLEAVED,
                                1, 16000, 1, 64000);
    if (rc < 0) { close_pcm(pcm); return -1; }
    return 0;
}
static void stop_locked(echo_audio_t *audio) {
    audio->status.playing = audio->status.listen = audio->status.talk = false;
    audio->count = audio->head = audio->current_count = audio->current_offset = 0;
    audio->deadline = 0;
    close_pcm(&audio->capture); close_pcm(&audio->playback);
}
static void *audio_worker(void *context) {
    echo_audio_t *audio = context;
    int16_t microphone[512];
    for (;;) {
        size_t captured = 0;
        pthread_mutex_lock(&audio->lock);
        bool closing = audio->closing;
        if (audio->deadline && echo_now_ms() >= audio->deadline) stop_locked(audio);
        if (audio->capture && audio->status.listen && !audio->status.talk) {
            snd_pcm_sframes_t count = snd_pcm_readi(audio->capture, microphone, 512);
            if (count > 0) {
                captured = count;
                unsigned peak = 0;
                for (size_t i = 0; i < captured; i++) {
                    unsigned level = microphone[i] < 0 ? -(int)microphone[i] : microphone[i];
                    if (level > peak) peak = level;
                }
                audio->status.mic_peak = peak; audio->status.tx_frames++;
            } else if (count < 0 && count != -EAGAIN && snd_pcm_recover(audio->capture, count, 1) < 0) {
                close_pcm(&audio->capture); audio->status.listen = false;
            }
        }
        if (audio->playback) {
            if (!audio->current_count && audio->count) {
                audio->current_count = audio->lengths[audio->head];
                memcpy(audio->current, audio->queue[audio->head], audio->current_count * 2);
                audio->head = (audio->head + 1) % 8; audio->count--;
                for (size_t i = 0; i < audio->current_count; i++)
                    audio->current[i] = audio->current[i] * audio->status.volume / 100;
            } else if (!audio->current_count && audio->status.playing && echo_now_ms() >= audio->melody_next) {
                static const unsigned notes[] = {262,330,392,523};
                unsigned frequency = notes[(audio->phase / 16000) % 4];
                for (size_t i = 0; i < 512; i++)
                    audio->current[i] = 6000 * audio->status.volume / 100 *
                        sin(6.283185307179586 * frequency * (audio->phase + i) / 16000);
                audio->phase += 512; audio->current_count = 512;
                audio->melody_next = echo_now_ms() + 32;
            }
            if (audio->current_count) {
                snd_pcm_sframes_t sent = snd_pcm_writei(audio->playback,
                    audio->current + audio->current_offset, audio->current_count - audio->current_offset);
                if (sent > 0) {
                    audio->current_offset += sent;
                    if (audio->current_offset == audio->current_count)
                        audio->current_offset = audio->current_count = 0;
                } else if (sent < 0 && sent != -EAGAIN && snd_pcm_recover(audio->playback, sent, 1) < 0) {
                    close_pcm(&audio->playback); audio->status.playing = audio->status.talk = false;
                    audio->current_count = audio->current_offset = audio->count = 0;
                }
            }
        }
        pthread_mutex_unlock(&audio->lock);
        /* Never call application code while holding a driver mutex. */
        if (captured && audio->on_capture) audio->on_capture(audio->context, microphone, captured);
        if (closing) break;
        echo_sleep_ms(5);
    }
    return NULL;
}
int echo_audio_init(echo_audio_t *audio, const char *device, bool enabled,
                    echo_audio_capture_fn callback, void *context) {
    memset(audio, 0, sizeof(*audio));
    pthread_mutex_init(&audio->lock, NULL);
    snprintf(audio->device, sizeof(audio->device), "%s", device);
    audio->enabled = enabled; audio->status.volume = 30;
    audio->on_capture = callback; audio->context = context;
    if (pthread_create(&audio->thread, NULL, audio_worker, audio)) {
        pthread_mutex_destroy(&audio->lock); return -1;
    }
    return 0;
}
int echo_audio_control(echo_audio_t *audio, const char *key, bool value, double volume) {
    int rc = 0;
    pthread_mutex_lock(&audio->lock);
    if (!strcmp(key, "audio_volume")) {
        if (!isfinite(volume) || volume < 0 || volume > 100) rc = -2;
        else audio->status.volume = volume;
    } else if (!strcmp(key, "audio_playing")) {
        stop_locked(audio);
        if (value && open_pcm(audio, &audio->playback, SND_PCM_STREAM_PLAYBACK)) rc = -1;
        else audio->status.playing = value;
    } else if (!strcmp(key, "voice_talk") || !strcmp(key, "voice_listen")) {
        if (audio->status.playing) stop_locked(audio);
        if (!strcmp(key, "voice_talk")) {
            if (value && open_pcm(audio, &audio->playback, SND_PCM_STREAM_PLAYBACK)) rc = -1;
            else {
                audio->status.talk = value;
                audio->count = audio->head = audio->current_count = audio->current_offset = 0;
                if (!value) close_pcm(&audio->playback);
                if (audio->capture) { snd_pcm_drop(audio->capture); snd_pcm_prepare(audio->capture); }
            }
        } else {
            if (value && open_pcm(audio, &audio->capture, SND_PCM_STREAM_CAPTURE)) rc = -1;
            else { audio->status.listen = value; if (!value) close_pcm(&audio->capture); }
        }
        if (!rc) audio->deadline = echo_now_ms() + 2500;
    } else rc = -2;
    pthread_mutex_unlock(&audio->lock);
    return rc;
}
int echo_audio_receive(echo_audio_t *audio, const unsigned char *bytes, size_t length) {
    if (!length || length > 1024 || length % 2) return -1;
    pthread_mutex_lock(&audio->lock);
    if (!audio->status.talk || !audio->playback) { pthread_mutex_unlock(&audio->lock); return -1; }
    if (audio->count == 8) { audio->head = (audio->head + 1) % 8; audio->count--; }
    size_t index = (audio->head + audio->count) % 8;
    for (size_t i = 0; i < length / 2; i++)
        audio->queue[index][i] = (int16_t)((unsigned)bytes[2*i] | (unsigned)bytes[2*i+1] << 8);
    audio->lengths[index] = length / 2; audio->count++; audio->status.rx_frames++;
    pthread_mutex_unlock(&audio->lock);
    return 0;
}
void echo_audio_stop(echo_audio_t *audio) {
    pthread_mutex_lock(&audio->lock); stop_locked(audio); pthread_mutex_unlock(&audio->lock);
}
echo_audio_status_t echo_audio_status(echo_audio_t *audio) {
    pthread_mutex_lock(&audio->lock); echo_audio_status_t status = audio->status;
    pthread_mutex_unlock(&audio->lock); return status;
}
void echo_audio_destroy(echo_audio_t *audio) {
    pthread_mutex_lock(&audio->lock); audio->closing = true; pthread_mutex_unlock(&audio->lock);
    pthread_join(audio->thread, NULL); echo_audio_stop(audio); pthread_mutex_destroy(&audio->lock);
}
