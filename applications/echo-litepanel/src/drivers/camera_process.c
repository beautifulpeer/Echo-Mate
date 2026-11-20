#define _GNU_SOURCE
#include "echo/camera.h"
#include "echo/platform.h"
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
extern char **environ;

static void *supervisor(void *context) {
    echo_camera_t *camera = context;
    while (!echo_quit) {
        pid_t pid;
        posix_spawn_file_actions_t actions;
        posix_spawn_file_actions_init(&actions);
        posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, "/dev/null", O_WRONLY, 0);
        char *args[] = {camera->program, NULL};
        int rc = posix_spawn(&pid, camera->program, &actions, NULL, args, environ);
        posix_spawn_file_actions_destroy(&actions);
        if (!rc) {
            int status;
            while (!echo_quit && waitpid(pid, &status, WNOHANG) == 0) echo_sleep_ms(100);
            if (echo_quit) {
                kill(pid, SIGTERM);
                unsigned n;
                for (n = 0; n < 20 && waitpid(pid, &status, WNOHANG) == 0; n++) echo_sleep_ms(100);
                if (n == 20) { kill(pid, SIGKILL); waitpid(pid, &status, 0); }
            }
        }
        if (!echo_quit) echo_log("Camera process unavailable; retry in 10s (check sensor/IQ files)");
        for (int n = 0; n < 100 && !echo_quit; n++) echo_sleep_ms(100);
    }
    return NULL;
}
int echo_camera_init(echo_camera_t *camera, const char *program, const char *path, bool enabled) {
    memset(camera, 0, sizeof(*camera));
    snprintf(camera->program, sizeof(camera->program), "%s", program);
    snprintf(camera->path, sizeof(camera->path), "%s", path);
    camera->enabled = enabled;
    if (enabled) {
        mkdir("/tmp/echo-litepanel", 0755);
        return pthread_create(&camera->thread, NULL, supervisor, camera) ? -1 : 0;
    }
    return 0;
}
int echo_camera_snapshot(echo_camera_t *camera, echo_jpeg_t *frame) {
    memset(frame, 0, sizeof(*frame)); frame->age_ms = -1;
    int fd = open(camera->path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    struct stat stat;
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    if (fstat(fd, &stat) || stat.st_size < 4 || stat.st_size > ECHO_JPEG_MAX) { close(fd); return -1; }
    long age = (now.tv_sec - stat.st_mtim.tv_sec) * 1000 + (now.tv_nsec - stat.st_mtim.tv_nsec) / 1000000;
    if (age < -1000 || age >= 3000) { close(fd); return -1; }
    frame->data = malloc(stat.st_size);
    if (!frame->data) { close(fd); return -1; }
    size_t used = 0;
    while (used < (size_t)stat.st_size) {
        ssize_t count = read(fd, frame->data + used, stat.st_size - used);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) break;
        used += count;
    }
    close(fd);
    if (used != (size_t)stat.st_size || frame->data[0] != 0xff || frame->data[1] != 0xd8 ||
        frame->data[used-2] != 0xff || frame->data[used-1] != 0xd9) {
        echo_camera_frame_free(frame); return -1;
    }
    frame->length = used; frame->age_ms = age < 0 ? 0 : age;
    frame->sequence = (uint64_t)stat.st_mtim.tv_sec * 1000 + stat.st_mtim.tv_nsec / 1000000;
    return 0;
}
void echo_camera_frame_free(echo_jpeg_t *frame) { free(frame->data); memset(frame, 0, sizeof(*frame)); }
void echo_camera_destroy(echo_camera_t *camera) { if (camera->enabled) pthread_join(camera->thread, NULL); }
