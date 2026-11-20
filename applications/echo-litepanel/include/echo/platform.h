#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <signal.h>

extern volatile sig_atomic_t echo_quit;
uint64_t echo_now_ms(void);
void echo_sleep_ms(unsigned ms);
void echo_log(const char *format, ...) __attribute__((format(printf, 1, 2)));
int echo_write_file(const char *path, const char *text);
int echo_listener(const char *bind_address, unsigned port, int type);
int echo_send_all(int fd, const void *data, size_t length, unsigned timeout_ms);
