#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <pthread.h>
#include <sys/types.h>

#define ECHO_JPEG_MAX (512 * 1024)
typedef struct {
    pthread_t thread;
    bool enabled;
    char program[256], path[256];
} echo_camera_t;
typedef struct {
    unsigned char *data;
    size_t length;
    uint32_t sequence;
    long age_ms;
} echo_jpeg_t;
int echo_camera_init(echo_camera_t *camera, const char *program, const char *path, bool enabled);
int echo_camera_snapshot(echo_camera_t *camera, echo_jpeg_t *frame);
void echo_camera_frame_free(echo_jpeg_t *frame);
void echo_camera_destroy(echo_camera_t *camera);
