#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <termios.h>
#include <unistd.h>

#define SERIAL_PATH "/dev/ttyGS0"
#define FRAME_PATH "/run/usb-display.rgb565"
#define PANEL_WIDTH 320
#define PANEL_HEIGHT 240
#define FRAME_SIZE (PANEL_WIDTH * PANEL_HEIGHT * 2)

struct __attribute__((packed)) frame_header {
    uint8_t magic[4];
    uint16_t width;
    uint16_t height;
    uint32_t payload_size;
    uint32_t sequence;
};

static ssize_t read_full(int fd, void *buffer, size_t length) {
    uint8_t *cursor = (uint8_t *)buffer;
    size_t done = 0;
    while (done < length) {
        ssize_t count = read(fd, cursor + done, length - done);
        if (count == 0) return 0;
        if (count < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        done += (size_t)count;
    }
    return (ssize_t)done;
}

static int read_header_sync(int fd, struct frame_header *header) {
    static const uint8_t magic[4] = { 'R', 'V', 'D', 'S' };
    unsigned matched = 0;
    uint8_t byte;
    while (read_full(fd, &byte, 1) == 1) {
        if (byte == magic[matched]) {
            if (++matched == sizeof(magic)) {
                memcpy(header->magic, magic, sizeof(magic));
                return read_full(fd, &header->width,
                                 sizeof(*header) - sizeof(header->magic)) > 0 ? 1 : 0;
            }
        } else {
            matched = (byte == magic[0]) ? 1 : 0;
        }
    }
    return 0;
}

int main(void) {
    int frame_fd = open(FRAME_PATH, O_CREAT | O_RDWR, 0660);
    if (frame_fd < 0 || ftruncate(frame_fd, 4 + FRAME_SIZE) != 0) return 1;
    uint8_t *shared = mmap(NULL, 4 + FRAME_SIZE, PROT_READ | PROT_WRITE,
                           MAP_SHARED, frame_fd, 0);
    if (shared == MAP_FAILED) return 1;

    for (;;) {
        int serial = open(SERIAL_PATH, O_RDONLY | O_NOCTTY);
        if (serial < 0) { sleep(1); continue; }
        struct termios tio;
        if (tcgetattr(serial, &tio) == 0) {
            cfmakeraw(&tio);
            tcsetattr(serial, TCSANOW, &tio);
        }
        fprintf(stderr, "usb_displayd_serial: receiver ready\n");
        for (;;) {
            struct frame_header header;
            if (!read_header_sync(serial, &header)) break;
            if (header.width != PANEL_WIDTH || header.height != PANEL_HEIGHT ||
                header.payload_size != FRAME_SIZE) {
                continue;
            }
            if (read_full(serial, shared + 4, FRAME_SIZE) <= 0) break;
            __sync_synchronize();
            *(volatile uint32_t *)shared = header.sequence;
        }
        close(serial);
        sleep(1);
    }
}
