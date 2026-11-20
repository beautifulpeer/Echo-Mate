#pragma once
#include "echo/app.h"

/* Each network worker owns its sockets. No driver includes this header. */
void *echo_tcp_run(void *app);
void *echo_mqtt_run(void *app);
void *echo_http_run(void *app);
void *echo_discovery_run(void *app);

typedef struct {
    unsigned char *data;
    size_t length, offset;
    uint64_t created;
} echo_packet_t;
typedef struct {
    pthread_mutex_t lock;
    echo_packet_t entries[16];
    size_t head, count;
    bool closed;
} echo_queue_t;
void echo_queue_init(echo_queue_t *queue);
int echo_queue_push(void *queue, const void *data, size_t length);
int echo_queue_pop(echo_queue_t *queue, echo_packet_t *packet);
void echo_queue_close(echo_queue_t *queue);
void echo_queue_destroy(echo_queue_t *queue);
