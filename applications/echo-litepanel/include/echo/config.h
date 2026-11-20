#pragma once
#include <stdbool.h>

typedef struct {
    char name[65], bind_address[64], gpio_root[256], audio_device[128];
    char camera_program[256], frame_path[256], cloud_file[256];
    unsigned tcp_port, discovery_port, http_port, stream_port;
    bool audio_enabled, camera_enabled;
} echo_config_t;

typedef struct {
    char host[256], device_id[65], username[128], password[256], ca_file[512];
    unsigned port;
    double camera_fps;
    bool tls;
} echo_cloud_config_t;

void echo_config_defaults(echo_config_t *config);
/* 0: configured, 1: file absent/cloud deliberately reserved, -1: invalid. */
int echo_cloud_config_load(const char *path, echo_cloud_config_t *config);
