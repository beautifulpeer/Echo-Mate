#define _GNU_SOURCE
#include "echo/platform.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

volatile sig_atomic_t echo_quit;

uint64_t echo_now_ms(void) {
    struct timespec time;
    clock_gettime(CLOCK_MONOTONIC, &time);
    return (uint64_t)time.tv_sec * 1000 + time.tv_nsec / 1000000;
}
void echo_sleep_ms(unsigned ms) {
    struct timespec time = {ms / 1000, (long)(ms % 1000) * 1000000};
    while (nanosleep(&time, &time) && errno == EINTR && !echo_quit) {}
}
void echo_log(const char *format, ...) {
    va_list args;
    va_start(args, format);
    flockfile(stderr);
    fprintf(stderr, "[%llu] ", (unsigned long long)echo_now_ms());
    vfprintf(stderr, format, args);
    fputc('\n', stderr);
    funlockfile(stderr);
    va_end(args);
}
int echo_write_file(const char *path, const char *text) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    size_t length = strlen(text);
    ssize_t result;
    do { result = write(fd, text, length); } while (result < 0 && errno == EINTR);
    close(fd);
    return result == (ssize_t)length ? 0 : -1;
}
int echo_listener(const char *address, unsigned port, int type) {
    int fd = socket(AF_INET, type | SOCK_NONBLOCK | SOCK_CLOEXEC, 0), yes = 1;
    if (fd < 0) return -1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    struct sockaddr_in local = {.sin_family = AF_INET, .sin_port = htons(port)};
    if (inet_pton(AF_INET, address, &local.sin_addr) != 1 ||
        bind(fd, (struct sockaddr *)&local, sizeof(local)) ||
        (type == SOCK_STREAM && listen(fd, 4))) {
        close(fd);
        return -1;
    }
    return fd;
}
int echo_send_all(int fd, const void *data, size_t length, unsigned timeout) {
    const unsigned char *bytes = data;
    uint64_t deadline = echo_now_ms() + timeout;
    while (length && !echo_quit && echo_now_ms() < deadline) {
        ssize_t sent = send(fd, bytes, length, MSG_NOSIGNAL | MSG_DONTWAIT);
        if (sent > 0) { bytes += sent; length -= sent; continue; }
        if (sent < 0 && errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK) return -1;
        struct pollfd pollfd = {.fd = fd, .events = POLLOUT};
        if (poll(&pollfd, 1, 20) < 0 && errno != EINTR) return -1;
    }
    return length ? -1 : 0;
}
