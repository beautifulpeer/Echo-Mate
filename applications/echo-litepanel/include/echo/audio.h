#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <pthread.h>
#include <alsa/asoundlib.h>

typedef void (*echo_audio_capture_fn)(void *context, const int16_t *pcm, size_t samples);
typedef struct {
    double volume;
    bool playing, listen, talk;
    uint32_t rx_frames, tx_frames;
    unsigned mic_peak;
} echo_audio_status_t;
typedef struct {
    pthread_mutex_t lock;
    pthread_t thread;
    bool enabled, closing;
    char device[128];
    snd_pcm_t *capture, *playback;
    echo_audio_status_t status;
    uint64_t deadline, melody_next;
    unsigned phase;
    int16_t queue[8][512], current[512];
    size_t lengths[8], head, count, current_count, current_offset;
    echo_audio_capture_fn on_capture;
    void *context;
} echo_audio_t;

int echo_audio_init(echo_audio_t *audio, const char *device, bool enabled,
                    echo_audio_capture_fn callback, void *context);
int echo_audio_control(echo_audio_t *audio, const char *key, bool enabled, double volume);
int echo_audio_receive(echo_audio_t *audio, const unsigned char *pcm, size_t length);
void echo_audio_stop(echo_audio_t *audio);
echo_audio_status_t echo_audio_status(echo_audio_t *audio);
void echo_audio_destroy(echo_audio_t *audio);
