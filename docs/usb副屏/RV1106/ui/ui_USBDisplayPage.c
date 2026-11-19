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

static lv_obj_t *s_image;
static lv_obj_t *s_status;
static lv_timer_t *s_timer;
static uint8_t *s_image_data;
static uint8_t *s_shared;
static int s_shared_fd = -1;
static uint32_t s_last_sequence;

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

static void display_timer_cb(lv_timer_t *timer)
{
    (void)timer;
    if (open_shared_frame() != 0) {
        lv_label_set_text(s_status, "Waiting for USB display...");
        lv_obj_clear_flag(s_status, LV_OBJ_FLAG_HIDDEN);
        return;
    }

    uint32_t before = *(volatile uint32_t *)s_shared;
    if (before == 0 || before == s_last_sequence)
        return;

    memcpy(s_image_data, s_shared + 4, FRAME_SIZE);
    __sync_synchronize();
    uint32_t after = *(volatile uint32_t *)s_shared;
    if (before != after)
        return;

    s_last_sequence = after;
    lv_obj_add_flag(s_status, LV_OBJ_FLAG_HIDDEN);
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

    s_status = lv_label_create(screen);
    lv_label_set_text(s_status, "Waiting for USB display...");
    lv_obj_set_style_text_color(s_status, lv_color_white(), LV_PART_MAIN);
    lv_obj_center(s_status);

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
