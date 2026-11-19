// RV1106 hand gesture demo main (YOLOv5 person detector + hand landmarks)
//
// Pipeline (per frame):
//   1. capture BGR frame
//   2. letterbox to 640x640, write into det_input_mem
//   3. yolov5 inference -> decode person bboxes
//   4. for each person: crop upper-half ROI to 224x224 -> lm_input_mem
//   5. hand_landmarks inference -> 21 landmarks + handedness
//   6. gesture_classifier rule -> label
//   7. draw bbox + skeleton + label, blit to /dev/fb0

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <getopt.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/fb.h>
#include <time.h>

#include <opencv2/core/core.hpp>
#include <opencv2/highgui/highgui.hpp>
#include <opencv2/imgproc/imgproc.hpp>

#include "hand_landmark.h"
#include "gesture_classifier.h"
#include "image_utils.h"
#include "image_drawing.h"
#include "file_utils.h"

#define DET_INPUT_W 640
#define DET_INPUT_H 640
#define LM_INPUT_W  224
#define LM_INPUT_H  224

static const int HAND_EDGES[][2] = {
    {0,1},{1,2},{2,3},{3,4},
    {0,5},{5,6},{6,7},{7,8},
    {5,9},{9,10},{10,11},{11,12},
    {9,13},{13,14},{14,15},{15,16},
    {13,17},{17,18},{18,19},{19,20},
    {0,17}
};
#define NUM_EDGES (sizeof(HAND_EDGES)/sizeof(HAND_EDGES[0]))

static void letterbox_bgr(const cv::Mat &src, cv::Mat &dst,
                          int dst_w, int dst_h,
                          float &scale, float &pad_x, float &pad_y) {
    scale = fminf((float)dst_w / src.cols, (float)dst_h / src.rows);
    int new_w = (int)(src.cols * scale);
    int new_h = (int)(src.rows * scale);
    pad_x = (dst_w - new_w) * 0.5f;
    pad_y = (dst_h - new_h) * 0.5f;
    cv::Mat resized;
    cv::resize(src, resized, cv::Size(new_w, new_h), 0, 0, cv::INTER_LINEAR);
    int top = (int)pad_y, left = (int)pad_x;
    int right = dst_w - new_w - left;
    int bottom = dst_h - new_h - top;
    cv::copyMakeBorder(resized, dst, top, bottom, left, right,
                       cv::BORDER_CONSTANT, cv::Scalar(114,114,114));
}

static void bgr_to_rgb_buffer(const cv::Mat &bgr, unsigned char *dst) {
    cv::Mat rgb;
    cv::cvtColor(bgr, rgb, cv::COLOR_BGR2RGB);
    memcpy(dst, rgb.data, rgb.total() * 3);
}

static void crop_lm_roi(const cv::Mat &bgr, const float person_box[4],
                        unsigned char *dst_rgb) {
    int img_w = bgr.cols, img_h = bgr.rows;
    float cx = person_box[0] + person_box[2] * 0.5f;
    float cy = person_box[1] + person_box[3] * 0.30f;
    float side = fmaxf(person_box[2], person_box[3] * 0.65f) * 1.2f;
    float half = side * 0.5f;
    int x0 = (int)fmaxf(0.f, cx - half);
    int y0 = (int)fmaxf(0.f, cy - half);
    int x1 = (int)fminf((float)img_w, cx + half);
    int y1 = (int)fminf((float)img_h, cy + half);
    if (x1 - x0 < 8)  x1 = x0 + 8;
    if (y1 - y0 < 8)  y1 = y0 + 8;
    cv::Rect roi(x0, y0, x1 - x0, y1 - y0);
    cv::Mat crop_bgr = bgr(roi).clone();
    cv::Mat resized;
    cv::resize(crop_bgr, resized, cv::Size(LM_INPUT_W, LM_INPUT_H), 0, 0, cv::INTER_LINEAR);
    cv::Mat rgb;
    cv::cvtColor(resized, rgb, cv::COLOR_BGR2RGB);
    memcpy(dst_rgb, rgb.data, LM_INPUT_W * LM_INPUT_H * 3);
}

static void draw_skeleton(cv::Mat &img, const hand_result_t &hr) {
    int W = img.cols, H = img.rows;
    auto to_pt = [&](int i) {
        return cv::Point((int)(hr.landmarks[i].x * W),
                         (int)(hr.landmarks[i].y * H));
    };
    for (size_t i = 0; i < NUM_EDGES; i++) {
        cv::Point a = to_pt(HAND_EDGES[i][0]);
        cv::Point b = to_pt(HAND_EDGES[i][1]);
        cv::line(img, a, b, cv::Scalar(0, 255, 0), 2, cv::LINE_AA);
    }
    for (int i = 0; i < NUM_LANDMARKS; i++) {
        cv::Point p = to_pt(i);
        cv::Scalar col = (i == 4 || i == 8 || i == 12 || i == 16 || i == 20)
                          ? cv::Scalar(0, 0, 255)
                          : cv::Scalar(255, 0, 0);
        cv::circle(img, p, 4, col, -1, cv::LINE_AA);
    }
    cv::Rect person((int)hr.person_box[0], (int)hr.person_box[1],
                    (int)hr.person_box[2], (int)hr.person_box[3]);
    cv::rectangle(img, person, cv::Scalar(0, 200, 0), 2);
    cv::Rect hand((int)hr.hand_box[0], (int)hr.hand_box[1],
                  (int)hr.hand_box[2], (int)hr.hand_box[3]);
    cv::rectangle(img, hand, cv::Scalar(255, 200, 0), 1);
}

static void usage(const char *prog) {
    fprintf(stderr, "Usage: %s [--camera N] [--width W] [--height H] [deploy_dir]\n", prog); fflush(stderr);
    fprintf(stderr, "  deploy_dir default: current directory. Models in <deploy_dir>/model/.\n"); fflush(stderr);
}

int main(int argc, char **argv) {
    int cam_id = 0;
    int cam_w = 1280, cam_h = 720;
    const char *deploy_dir = ".";

    static struct option opts[] = {
        {"camera", required_argument, 0, 'c'},
        {"width",  required_argument, 0, 'w'},
        {"height", required_argument, 0, 'h'},
        {"help",   no_argument,       0, '?'},
        {0,0,0,0}
    };
    int o, idx;
    while ((o = getopt_long(argc, argv, "c:w:h:?", opts, &idx)) != -1) {
        switch (o) {
        case 'c': cam_id = atoi(optarg); break;
        case 'w': cam_w = atoi(optarg); break;
        case 'h': cam_h = atoi(optarg); break;
        case '?': usage(argv[0]); return 0;
        }
    }
    if (optind < argc) deploy_dir = argv[optind];

    char det_path[512], lm_path[512];
    snprintf( det_path, sizeof(det_path), "%s/model/yolov5s.rknn", deploy_dir); fflush(stderr);
    snprintf( lm_path,  sizeof(lm_path),  "%s/model/hand_landmarks.rknn", deploy_dir); fflush(stderr);
    fprintf(stderr, "det:    %s\nlm:     %s\n", det_path, lm_path); fflush(stderr);

    system("RkLunch-stop.sh");

    int fb = open("/dev/fb0", O_RDWR);
    int fb_w = 0, fb_h = 0, fb_pix = 0;
    void *fb_buf = NULL; size_t fb_size = 0;
    cv::Mat fb_mat;
    if (fb < 0) {
        fprintf(stderr, "/dev/fb0 not available (headless)\n"); fflush(stderr);
        fb_w = cam_w; fb_h = cam_h; fb_pix = 4;
    } else {
        struct fb_var_screeninfo v; struct fb_fix_screeninfo f;
        ioctl(fb, FBIOGET_VSCREENINFO, &v);
        ioctl(fb, FBIOGET_FSCREENINFO, &f);
        fb_w = v.xres; fb_h = v.yres; fb_pix = v.bits_per_pixel / 8;
        fb_size = fb_w * fb_h * fb_pix;
        fb_buf = mmap(NULL, fb_size, PROT_READ|PROT_WRITE, MAP_SHARED, fb, 0);
        if (fb_pix == 4)      fb_mat = cv::Mat(fb_h, fb_w, CV_8UC4);
        else if (fb_pix == 2) fb_mat = cv::Mat(fb_h, fb_w, CV_16UC1);
        else                  fb_mat = cv::Mat(fb_h, fb_w, CV_8UC3);
    }

    cv::VideoCapture cap;
    cap.set(cv::CAP_PROP_FRAME_WIDTH,  cam_w);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, cam_h);
    if (!cap.open(cam_id)) {
        fprintf(stderr, "Failed to open camera %d\n", cam_id); fflush(stderr);
        return -1;
    }
    fprintf(stderr, "Camera %d opened at %dx%d\n", cam_id, cam_w, cam_h); fflush(stderr);

    hand_landmark_ctx_t hl;
    if (init_hand_landmark(det_path, lm_path, &hl) != 0) {
        fprintf(stderr, "init_hand_landmark failed\n"); fflush(stderr);
        return -1;
    }

    cv::Mat det_lb(DET_INPUT_H, DET_INPUT_W, CV_8UC3, cv::Scalar(114,114,114));
    cv::Mat lm_lb (LM_INPUT_H,   LM_INPUT_W,   CV_8UC3, cv::Scalar(114,114,114));
    unsigned char *det_buf = (unsigned char *)hl.det_input_mem->virt_addr;
    unsigned char *lm_buf  = (unsigned char *)hl.lm_input_mem->virt_addr;

    float person_boxes[8*5];
    int max_persons = 4;

    clock_t t0 = clock();
    int frame_count = 0; float fps = 0.f;
    char fps_text[64];

    long frame_total = 0;
    for (;;) {
        cv::Mat bgr;
        cap >> bgr;
        if (++frame_total % 30 == 0) { fprintf(stderr, "frame %ld\n", frame_total); fflush(stderr); }
        if (bgr.empty()) continue;

        float d_scale, d_px, d_py;
        letterbox_bgr(bgr, det_lb, DET_INPUT_W, DET_INPUT_H, d_scale, d_px, d_py);
        bgr_to_rgb_buffer(det_lb, det_buf);

        int n = detect_persons(&hl, bgr.data, bgr.cols, bgr.rows,
                               person_boxes, max_persons);

        frame_count++;
        if (frame_count % 30 == 0) {
            fps = (float)CLOCKS_PER_SEC / (clock() - t0) * 30.f;
            t0 = clock();
        }

        hand_result_t hr;
        memset(&hr, 0, sizeof(hr));
        char gesture_name[GESTURE_NAME_MAX] = "Unknown";
        if (n > 0) {
            int best = 0;
            for (int i = 1; i < n; i++)
                if (person_boxes[i*5+4] > person_boxes[best*5+4]) best = i;
            const float *pb = &person_boxes[best*5];

            crop_lm_roi(bgr, pb, lm_buf);

            if (detect_landmarks(&hl, bgr.data, bgr.cols, bgr.rows, pb, &hr) == 0) {
                classify_gesture(hr.landmarks, NUM_LANDMARKS, hr.handedness,
                                 gesture_name, sizeof(gesture_name));
                draw_skeleton(bgr, hr);
            }
        }

        snprintf( fps_text, sizeof(fps_text), "FPS %.1f  Person: %d", fps, n); fflush(stderr);
        cv::putText(bgr, fps_text, cv::Point(12, 32),
                    cv::FONT_HERSHEY_SIMPLEX, 0.7, cv::Scalar(0,255,0), 2);
        cv::putText(bgr, gesture_name, cv::Point(12, 64),
                    cv::FONT_HERSHEY_SIMPLEX, 0.8, cv::Scalar(0,255,255), 2);

        if (fb >= 0 && fb_buf) {
            cv::Mat show;
            if (fb_w != bgr.cols || fb_h != bgr.rows)
                cv::resize(bgr, show, cv::Size(fb_w, fb_h), 0, 0, cv::INTER_LINEAR);
            else
                show = bgr;
            if (fb_pix == 4) {
                cv::cvtColor(show, fb_mat, cv::COLOR_BGR2BGRA);
                memcpy(fb_buf, fb_mat.data, fb_size);
            } else if (fb_pix == 2) {
                cv::cvtColor(show, fb_mat, cv::COLOR_BGR2BGR565);
                memcpy(fb_buf, fb_mat.data, fb_size);
            } else {
                memcpy(fb_buf, show.data, fb_size);
            }
        }
        if (cv::waitKey(1) == 27) break;
    }

    release_hand_landmark(&hl);
    if (fb >= 0) { munmap(fb_buf, fb_size); close(fb); }
    return 0;
}