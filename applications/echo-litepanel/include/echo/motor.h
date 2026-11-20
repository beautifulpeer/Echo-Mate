#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <pthread.h>

typedef struct {
    pthread_mutex_t lock;
    pthread_t thread;
    bool ready, closing;
    int direction;
    uint64_t deadline;
    char root[256];
} echo_motor_t;

int echo_motor_init(echo_motor_t *motor, const char *gpio_root);
int echo_motor_set(echo_motor_t *motor, const char *direction);
void echo_motor_stop(echo_motor_t *motor);
const char *echo_motor_direction(echo_motor_t *motor);
bool echo_motor_ready(echo_motor_t *motor);
void echo_motor_destroy(echo_motor_t *motor);
