#include "lvgl/lvgl.h"
#include "lvgl/demos/lv_demos.h"
#include <unistd.h>
#include <pthread.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>

#include "gui_app/common/lv_lib.h"
#include "gui_app/ui.h"

#define BOOT_ANIMATION_TIME_MS 5000
#define BOOT_FRAME_TIME_MS 40
#define BOOT_FRAME_COUNT 17

static void play_boot_animation(void)
{
    lv_obj_t *screen = lv_obj_create(NULL);
    lv_obj_remove_style_all(screen);
    lv_obj_set_size(screen, 320, 240);
    lv_obj_set_style_bg_color(screen, lv_color_black(), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);

    lv_obj_t *image = lv_image_create(screen);
    lv_obj_set_size(image, 320, 240);
    lv_obj_center(image);
    lv_screen_load(screen);

    uint32_t started = lv_tick_get();
    uint32_t next_frame = started;
    unsigned frame = 0;
    char path[96];
    while(lv_tick_elaps(started) < BOOT_ANIMATION_TIME_MS) {
        if((int32_t)(lv_tick_get() - next_frame) >= 0) {
            snprintf(path, sizeof(path),
                     "A:/root/bin/assets/usb-wait-frames/9/%03u.jpg", frame);
            lv_image_set_src(image, path);
            frame = (frame + 1) % BOOT_FRAME_COUNT;
            next_frame += BOOT_FRAME_TIME_MS;
        }
        lv_timer_handler();
        usleep(1000);
    }
}

static const char *getenv_default(const char *name, const char *dflt)
{
    return getenv(name) ? : dflt;
}

#if LV_USE_EVDEV
static void lv_linux_indev_init(void)
{
    lv_indev_t * touch;
    touch = lv_evdev_create(LV_INDEV_TYPE_POINTER, "/dev/input/event0");
}
#endif

#if LV_USE_LINUX_FBDEV
static void lv_linux_disp_init(void)
{
    const char *device = getenv_default("LV_LINUX_FBDEV_DEVICE", "/dev/fb0");
    lv_display_t * disp = lv_linux_fbdev_create();

    lv_linux_fbdev_set_file(disp, device);
}
#elif LV_USE_LINUX_DRM
static void lv_linux_disp_init(void)
{
    const char *device = getenv_default("LV_LINUX_DRM_CARD", "/dev/dri/card0");
    lv_display_t * disp = lv_linux_drm_create();

    lv_linux_drm_set_file(disp, device, -1);
}
#elif LV_USE_SDL
static void lv_linux_disp_init(void)
{
    const int width = atoi(getenv("LV_SDL_VIDEO_WIDTH") ? : "320");
    const int height = atoi(getenv("LV_SDL_VIDEO_HEIGHT") ? : "240");

    lv_sdl_window_create(width, height);
}

static void lv_linux_indev_init(void)
{
    lv_sdl_mouse_create();
}

#else
#error Unsupported configuration
#endif

int main(void)
{
    lv_init();

    /*Linux display device init*/
    lv_linux_disp_init();

    lv_linux_indev_init();

    /*Create a Demo*/
    // lv_demo_widgets();
    // lv_demo_widgets_start_slideshow();
    play_boot_animation();
    ui_init();
    /*Handle LVGL tasks*/
    while(1) {
        lv_timer_handler();
        usleep(1000);
    }

    return 0;
}
