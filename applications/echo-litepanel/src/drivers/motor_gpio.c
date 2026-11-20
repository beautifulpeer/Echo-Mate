#include "echo/motor.h"
#include "echo/platform.h"
#include <stdio.h>
#include <string.h>

/* 原 DeskBot 已验证的接线；右电机极性与左侧相反。 */
static const int pins[] = {32, 33, 35, 36};
static const char *names[] = {"stop", "forward", "backward", "left", "right"};
static const int levels[][4] = {{0,0,0,0}, {0,1,1,0}, {1,0,0,1}, {1,0,1,0}, {0,1,0,1}};

static int pin_write(echo_motor_t *motor, int index, const char *file, const char *value) {
    char path[320];
    snprintf(path, sizeof(path), "%s/gpio%d/%s", motor->root, pins[index], file);
    return echo_write_file(path, value);
}
static void stop_locked(echo_motor_t *motor) {
    for (int i = 0; i < 4; i++)
        if (pin_write(motor, i, "value", "0")) motor->ready = false;
    motor->direction = 0; motor->deadline = 0;
}
static void *watchdog(void *context) {
    echo_motor_t *motor = context;
    for (;;) {
        pthread_mutex_lock(&motor->lock);
        bool closing = motor->closing;
        if (motor->deadline && echo_now_ms() >= motor->deadline) stop_locked(motor);
        pthread_mutex_unlock(&motor->lock);
        if (closing) break;
        echo_sleep_ms(25);
    }
    return NULL;
}
int echo_motor_init(echo_motor_t *motor, const char *root) {
    memset(motor, 0, sizeof(*motor));
    snprintf(motor->root, sizeof(motor->root), "%s", root);
    pthread_mutex_init(&motor->lock, NULL);
    motor->ready = true;
    for (int i = 0; i < 4; i++) {
        char path[320], number[16];
        snprintf(path, sizeof(path), "%s/export", root);
        snprintf(number, sizeof(number), "%d", pins[i]);
        /* Already exported is normal. Direction write determines availability. */
        echo_write_file(path, number);
        if (pin_write(motor, i, "direction", "low")) motor->ready = false;
    }
    stop_locked(motor);
    if (!motor->ready) echo_log("Motor GPIO unavailable; vehicle capability disabled");
    if (pthread_create(&motor->thread, NULL, watchdog, motor)) {
        pthread_mutex_destroy(&motor->lock);
        return -1;
    }
    return 0;
}
int echo_motor_set(echo_motor_t *motor, const char *name) {
    int direction;
    for (direction = 0; direction < 5; direction++)
        if (name && !strcmp(name, names[direction])) break;
    if (direction == 5) return -2;
    pthread_mutex_lock(&motor->lock);
    int rc = 0;
    if (!motor->ready) rc = -1;
    else {
        if (direction != motor->direction) {
            stop_locked(motor);
            echo_sleep_ms(2);
            for (int i = 0; i < 4; i++)
                if (levels[direction][i] && pin_write(motor, i, "value", "1")) motor->ready = false;
        }
        if (!motor->ready) { stop_locked(motor); rc = -1; }
        else {
            motor->direction = direction;
            motor->deadline = direction ? echo_now_ms() + 700 : 0;
        }
    }
    pthread_mutex_unlock(&motor->lock);
    return rc;
}
void echo_motor_stop(echo_motor_t *motor) {
    pthread_mutex_lock(&motor->lock);
    stop_locked(motor);
    pthread_mutex_unlock(&motor->lock);
}
const char *echo_motor_direction(echo_motor_t *motor) {
    pthread_mutex_lock(&motor->lock);
    const char *name = names[motor->direction];
    pthread_mutex_unlock(&motor->lock);
    return name;
}
bool echo_motor_ready(echo_motor_t *motor) {
    pthread_mutex_lock(&motor->lock);
    bool ready = motor->ready;
    pthread_mutex_unlock(&motor->lock);
    return ready;
}
void echo_motor_destroy(echo_motor_t *motor) {
    pthread_mutex_lock(&motor->lock);
    motor->closing = true;
    stop_locked(motor);
    pthread_mutex_unlock(&motor->lock);
    pthread_join(motor->thread, NULL);
    pthread_mutex_destroy(&motor->lock);
}
