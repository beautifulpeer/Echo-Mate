#include "ui_USBDisplayPage.h"

#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#define DISP_WIDTH 320
#define DISP_HEIGHT 240
#define FRAME_SIZE (DISP_WIDTH * DISP_HEIGHT * 2)
#define SHARED_SIZE (4 + FRAME_SIZE)
#define FRAME_PATH "/run/usb-display.rgb565"
#define WAIT_ANIMATION_COUNT 8
#define WAIT_ANIMATION_TIME_MS 5000
#define STREAM_TIMEOUT_MS 2000
#define WAIT_FRAME_TIME_MS 100

static lv_obj_t *s_image;
static lv_obj_t *s_wait_image;
static lv_timer_t *s_timer;
static uint8_t *s_image_data;
static uint8_t *s_shared;
static int s_shared_fd = -1;
static uint32_t s_last_sequence;
static uint32_t s_last_frame_tick;
static uint32_t s_wait_switch_tick;
static unsigned s_wait_index;
static unsigned s_wait_frame;
static uint32_t s_wait_frame_tick;
static int s_sequence_initialized;
static int s_showing_stream;

static const unsigned s_wait_frame_counts[WAIT_ANIMATION_COUNT] = {
    51, 13, 23, 29, 12, 44, 1, 18
};

static lv_image_dsc_t s_image_desc = {
    .header.w = DISP_WIDTH,
    .header.h = DISP_HEIGHT,
    .data_size = FRAME_SIZE,
    .header.cf = LV_COLOR_FORMAT_RGB565,
    .data = NULL,
};

static void close_shared_frame(void)
{
    if (s_shared) {
        munmap(s_shared, SHARED_SIZE);
        s_shared = NULL;
    }
    if (s_shared_fd >= 0) {
        close(s_shared_fd);
        s_shared_fd = -1;
    }
}

static int open_shared_frame(void)
{
    if (s_shared)
        return 0;

    s_shared_fd = open(FRAME_PATH, O_RDONLY);
    if (s_shared_fd < 0)
        return -1;

    s_shared = mmap(NULL, SHARED_SIZE, PROT_READ, MAP_SHARED, s_shared_fd, 0);
    if (s_shared == MAP_FAILED) {
        s_shared = NULL;
        close_shared_frame();
        return -1;
    }
    return 0;
}

static void show_wait_animation(void)
{
    if (s_showing_stream) {
        s_showing_stream = 0;
        lv_obj_add_flag(s_image, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_wait_image, LV_OBJ_FLAG_HIDDEN);
    }
}

static void update_wait_animation(uint32_t now)
{
    show_wait_animation();
    if (lv_tick_elaps(s_wait_switch_tick) >= WAIT_ANIMATION_TIME_MS) {
        s_wait_index = (s_wait_index + 1) % WAIT_ANIMATION_COUNT;
        s_wait_frame = 0;
        s_wait_switch_tick = now;
        s_wait_frame_tick = 0;
    }
    if (s_wait_frame_tick == 0 || lv_tick_elaps(s_wait_frame_tick) >= WAIT_FRAME_TIME_MS) {
        char path[96];
        snprintf(path, sizeof(path),
                 "A:/root/bin/assets/usb-wait-frames/%u/%03u.jpg",
                 s_wait_index + 1, s_wait_frame);
        lv_image_set_src(s_wait_image, path);
        s_wait_frame = (s_wait_frame + 1) % s_wait_frame_counts[s_wait_index];
        s_wait_frame_tick = now;
    }
}

static void display_timer_cb(lv_timer_t *timer)
{
    (void)timer;
    uint32_t now = lv_tick_get();
    if (open_shared_frame() != 0) {
        update_wait_animation(now);
        return;
    }

    uint32_t before = *(volatile uint32_t *)s_shared;
    if (!s_sequence_initialized) {
        s_last_sequence = before;
        s_sequence_initialized = 1;
        update_wait_animation(now);
        return;
    }
    if (before == 0 || before == s_last_sequence) {
        if (!s_showing_stream || lv_tick_elaps(s_last_frame_tick) >= STREAM_TIMEOUT_MS)
            update_wait_animation(now);
        return;
    }

    memcpy(s_image_data, s_shared + 4, FRAME_SIZE);
    __sync_synchronize();
    uint32_t after = *(volatile uint32_t *)s_shared;
    if (before != after)
        return;

    s_last_sequence = after;
    s_last_frame_tick = now;
    s_showing_stream = 1;
    lv_obj_add_flag(s_wait_image, LV_OBJ_FLAG_HIDDEN);
    lv_obj_clear_flag(s_image, LV_OBJ_FLAG_HIDDEN);
    lv_img_set_src(s_image, &s_image_desc);
    lv_obj_invalidate(s_image);
}

static void gesture_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) != LV_EVENT_GESTURE)
        return;
    lv_dir_t direction = lv_indev_get_gesture_dir(lv_indev_get_act());
    if (direction == LV_DIR_LEFT || direction == LV_DIR_RIGHT)
        lv_lib_pm_OpenPrePage(&page_manager);
}

void ui_USBDisplayPage_init(void)
{
    s_last_sequence = 0;
    s_last_frame_tick = 0;
    s_wait_switch_tick = lv_tick_get();
    s_wait_index = 0;
    s_wait_frame = 0;
    s_wait_frame_tick = 0;
    s_sequence_initialized = 0;
    s_showing_stream = 0;
    s_image_data = malloc(FRAME_SIZE);
    if (!s_image_data) {
        ui_msgbox_info("Error", "USB display memory allocation failed");
        lv_lib_pm_OpenPrePage(&page_manager);
        return;
    }
    memset(s_image_data, 0, FRAME_SIZE);
    s_image_desc.data = s_image_data;

    lv_obj_t *screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(screen, lv_color_black(), LV_PART_MAIN);

    s_image = lv_img_create(screen);
    lv_obj_set_pos(s_image, 0, 0);
    lv_obj_set_size(s_image, DISP_WIDTH, DISP_HEIGHT);
    lv_img_set_src(s_image, &s_image_desc);
    lv_obj_add_flag(s_image, LV_OBJ_FLAG_HIDDEN);

    s_wait_image = lv_image_create(screen);
    lv_obj_set_size(s_wait_image, DISP_WIDTH, DISP_HEIGHT);
    lv_obj_center(s_wait_image);
    update_wait_animation(s_wait_switch_tick);

    lv_obj_add_event_cb(screen, gesture_cb, LV_EVENT_ALL, NULL);
    s_timer = lv_timer_create(display_timer_cb, 33, NULL);
    lv_scr_load_anim(screen, LV_SCR_LOAD_ANIM_MOVE_RIGHT, 100, 0, true);
}

void ui_USBDisplayPage_deinit(void)
{
    if (s_timer) {
        lv_timer_del(s_timer);
        s_timer = NULL;
    }
    close_shared_frame();
    free(s_image_data);
    s_image_data = NULL;
    s_image_desc.data = NULL;
}
