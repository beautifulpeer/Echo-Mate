#ifndef _RKNN_DEMO_HAND_LANDMARK_H_
#define _RKNN_DEMO_HAND_LANDMARK_H_

#include "rknn_api.h"
#include "common.h"

#if defined(RV1106_1103)
typedef struct {
    char *dma_buf_virt_addr;
    int   dma_buf_fd;
    int   size;
} rknn_dma_buf;
#endif

#define NUM_LANDMARKS 21
#define GESTURE_NAME_MAX 32

typedef struct {
    float x, y, z;
} landmark_t;

typedef struct {
    landmark_t landmarks[NUM_LANDMARKS];
    float handedness;
    float handedness_score;
    float presence_score;
    float hand_box[4];
    float person_box[5];
} hand_result_t;

typedef struct {
    rknn_context detector_ctx;
    rknn_context landmarks_ctx;

    rknn_input_output_num det_io;
    rknn_input_output_num lm_io;

    rknn_tensor_attr *det_input_attrs;
    rknn_tensor_attr *det_output_attrs;
    rknn_tensor_attr *lm_input_attrs;
    rknn_tensor_attr *lm_output_attrs;

    rknn_tensor_mem *det_input_mem;
    rknn_tensor_mem *det_output_mems[3];
    rknn_tensor_mem *lm_input_mem;
    rknn_tensor_mem *lm_output_mems[4];

    int det_model_w;
    int det_model_h;
    int lm_model_w;
    int lm_model_h;

    int det_stride_num;
    int det_anchor_per_stride;
    const float (*det_anchors)[3][2];

    bool det_is_quant;
    bool lm_is_quant;
} hand_landmark_ctx_t;

int init_hand_landmark(const char *detector_model_path,
                       const char *landmarks_model_path,
                       hand_landmark_ctx_t *ctx);

int release_hand_landmark(hand_landmark_ctx_t *ctx);

int detect_persons(hand_landmark_ctx_t *ctx,
                   const unsigned char *bgr888, int img_w, int img_h,
                   float person_boxes[], int max_persons);

int detect_landmarks(hand_landmark_ctx_t *ctx,
                     const unsigned char *bgr888, int img_w, int img_h,
                     const float person_box[4],
                     hand_result_t *out);

#endif