#pragma once
#include "echo/config.h"
#include "echo/motor.h"
#include "echo/audio.h"
#include "echo/camera.h"
#include "lp_wire.h"
#include <pthread.h>

/* Transport only supplies a bounded byte sender; business logic knows no sockets. */
typedef int (*echo_send_fn)(void *context, const void *data, size_t length);
typedef struct {
    pthread_mutex_t lock;
    pthread_t thread;
    echo_config_t config;
    echo_motor_t motor;
    echo_audio_t audio;
    echo_camera_t camera;
    void *session;
    echo_send_fn send;
    bool acknowledged;
    uint32_t capability_seq, sample_seq;
    uint64_t next_report;
    unsigned char buffer[LP_WIRE_MAX];
    size_t used;
} echo_app_t;
int echo_app_init(echo_app_t *app, const echo_config_t *config);
bool echo_app_open(echo_app_t *app, void *session, echo_send_fn send);
void echo_app_close(echo_app_t *app, void *session);
int echo_app_feed(echo_app_t *app, void *session, const unsigned char *bytes, size_t length);
bool echo_app_is_active(echo_app_t *app, void *session, bool require_ack);
void echo_app_destroy(echo_app_t *app);
