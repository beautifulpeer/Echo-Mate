// Two-stage RKNN pipeline for RV1106:
//   - YOLOv5 person detector (640x640) -> person bbox
//   - hand landmarks (224x224) -> 21 landmarks + handedness
// Stage-2 ROI = upper-half of the person bbox.

#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>

#include "hand_landmark.h"
#include "common.h"
#include "file_utils.h"
#include "image_utils.h"

#define DET_INPUT_W  640
#define DET_INPUT_H  640
#define LM_INPUT_W   224
#define LM_INPUT_H   224
#define PERSON_CLASS_ID 0

static const float YOLOV5_ANCHORS[3][3][2] = {
    { {10,13}, {16,30}, {33,23} },
    { {30,61}, {62,45}, {59,119} },
    { {116,90}, {156,198}, {373,326} }
};
static const int YOLOV5_STRIDES[3] = { 8, 16, 32 };
static const int YOLOV5_GRID_SIZES[3] = { 80, 40, 20 };

static int init_one_model(const char *path, rknn_context *ctx,
                          rknn_input_output_num *io_num,
                          rknn_tensor_attr **in_attrs_out,
                          rknn_tensor_attr **out_attrs_out,
                          rknn_tensor_mem **in_mem_out,
                          rknn_tensor_mem **out_mems_out, int max_out,
                          bool *is_quant_out,
                          int *model_w_out, int *model_h_out) {
    int ret = rknn_init(ctx, (char *)path, 0, 0, NULL);
    if (ret < 0) { printf("rknn_init fail %s: %d\n", path, ret); return -1; }
    ret = rknn_query(*ctx, RKNN_QUERY_IN_OUT_NUM, io_num, sizeof(*io_num));
    if (ret != 0) { printf("rknn_query IO num fail\n"); return -1; }

    rknn_tensor_attr *in_a = (rknn_tensor_attr *)calloc(io_num->n_input, sizeof(rknn_tensor_attr));
    for (int i = 0; i < io_num->n_input; i++) {
        in_a[i].index = i;
        ret = rknn_query(*ctx, RKNN_QUERY_NATIVE_INPUT_ATTR, &in_a[i], sizeof(rknn_tensor_attr));
        if (ret != 0) { printf("query input attr fail\n"); return -1; }
    }
    in_a[0].type = RKNN_TENSOR_UINT8;
    in_a[0].fmt  = RKNN_TENSOR_NHWC;

    rknn_tensor_attr *out_a = (rknn_tensor_attr *)calloc(io_num->n_output, sizeof(rknn_tensor_attr));
    for (int i = 0; i < io_num->n_output; i++) {
        out_a[i].index = i;
        ret = rknn_query(*ctx, RKNN_QUERY_NATIVE_NHWC_OUTPUT_ATTR, &out_a[i], sizeof(rknn_tensor_attr));
        if (ret != 0) { printf("query output attr fail\n"); return -1; }
    }

    *in_mem_out = rknn_create_mem(*ctx, in_a[0].size_with_stride);
    ret = rknn_set_io_mem(*ctx, *in_mem_out, &in_a[0]);
    if (ret != 0) { printf("set input mem fail\n"); return -1; }

    int n_out = io_num->n_output < max_out ? io_num->n_output : max_out;
    for (int i = 0; i < n_out; i++) {
        out_mems_out[i] = rknn_create_mem(*ctx, out_a[i].size_with_stride);
        ret = rknn_set_io_mem(*ctx, out_mems_out[i], &out_a[i]);
        if (ret != 0) { printf("set output mem fail (i=%d)\n", i); return -1; }
    }
    for (int i = n_out; i < max_out; i++) out_mems_out[i] = NULL;

    *is_quant_out = (out_a[0].qnt_type == RKNN_TENSOR_QNT_AFFINE_ASYMMETRIC);
    *in_attrs_out  = in_a;
    *out_attrs_out = out_a;

    if (in_a[0].fmt == RKNN_TENSOR_NCHW) {
        *model_h_out = in_a[0].dims[2];
        *model_w_out = in_a[0].dims[3];
    } else {
        *model_h_out = in_a[0].dims[1];
        *model_w_out = in_a[0].dims[2];
    }
    return 0;
}

int init_hand_landmark(const char *det_path, const char *lm_path,
                       hand_landmark_ctx_t *ctx) {
    memset(ctx, 0, sizeof(*ctx));
    if (init_one_model(det_path, &ctx->detector_ctx, &ctx->det_io,
                       &ctx->det_input_attrs, &ctx->det_output_attrs,
                       &ctx->det_input_mem, ctx->det_output_mems, 3,
                       &ctx->det_is_quant,
                       &ctx->det_model_w, &ctx->det_model_h) != 0) {
        return -1;
    }
    if (init_one_model(lm_path, &ctx->landmarks_ctx, &ctx->lm_io,
                       &ctx->lm_input_attrs, &ctx->lm_output_attrs,
                       &ctx->lm_input_mem, ctx->lm_output_mems, 4,
                       &ctx->lm_is_quant,
                       &ctx->lm_model_w, &ctx->lm_model_h) != 0) {
        return -1;
    }
    ctx->det_stride_num = 3;
    ctx->det_anchor_per_stride = 3;
    ctx->det_anchors = YOLOV5_ANCHORS;
    printf("detector: %dx%d, landmarks: %dx%d\n",
           ctx->det_model_w, ctx->det_model_h,
           ctx->lm_model_w,   ctx->lm_model_h);
    return 0;
}

int release_hand_landmark(hand_landmark_ctx_t *ctx) {
    if (ctx->detector_ctx) rknn_destroy(ctx->detector_ctx);
    if (ctx->landmarks_ctx) rknn_destroy(ctx->landmarks_ctx);
    if (ctx->det_input_attrs) free(ctx->det_input_attrs);
    if (ctx->det_output_attrs) free(ctx->det_output_attrs);
    if (ctx->lm_input_attrs) free(ctx->lm_input_attrs);
    if (ctx->lm_output_attrs) free(ctx->lm_output_attrs);
    if (ctx->det_input_mem)  { rknn_destroy_mem(ctx->detector_ctx,    ctx->det_input_mem);  free(ctx->det_input_mem); }
    if (ctx->lm_input_mem)    { rknn_destroy_mem(ctx->landmarks_ctx, ctx->lm_input_mem);    free(ctx->lm_input_mem); }
    for (int i = 0; i < 3; i++)
        if (ctx->det_output_mems[i]) { rknn_destroy_mem(ctx->detector_ctx, ctx->det_output_mems[i]); free(ctx->det_output_mems[i]); }
    for (int i = 0; i < 4; i++)
        if (ctx->lm_output_mems[i]) { rknn_destroy_mem(ctx->landmarks_ctx, ctx->lm_output_mems[i]); free(ctx->lm_output_mems[i]); }
    memset(ctx, 0, sizeof(*ctx));
    return 0;
}

static inline float sigmoid(float x) { return 1.0f / (1.0f + expf(-x)); }
static inline float deq(int8_t v, int32_t zp, float scale) {
    return ((float)v - (float)zp) * scale;
}

#define NUM_CANDIDATES 512
typedef struct {
    float x, y, w, h, score;
} candidate_t;

static int decode_one_stride(const int8_t *feat, int32_t zp, float scale,
                             int stride_idx, int W, int H,
                             float scale_ratio, float pad_x, float pad_y,
                             float img_w, float img_h, float score_thresh,
                             candidate_t *cands, int max_cands, int *n_cands) {
    int stride = YOLOV5_STRIDES[stride_idx];
    int anchors = 3;
    int classes = 80;
    int per_anchor = 5 + classes;

    for (int ay = 0; ay < H; ay++) {
        for (int ax = 0; ax < W; ax++) {
            for (int ai = 0; ai < anchors; ai++) {
                int base = (ay * W + ax) * anchors * per_anchor + ai * per_anchor;
                float tx = deq(feat[base + 0], zp, scale);
                float ty = deq(feat[base + 1], zp, scale);
                float tw = deq(feat[base + 2], zp, scale);
                float th = deq(feat[base + 3], zp, scale);
                float obj = sigmoid(deq(feat[base + 4], zp, scale));
                float pc  = sigmoid(deq(feat[base + 5 + PERSON_CLASS_ID], zp, scale));
                float conf = obj * pc;
                if (conf < score_thresh) continue;
                float aw = YOLOV5_ANCHORS[stride_idx][ai][0];
                float ah = YOLOV5_ANCHORS[stride_idx][ai][1];
                float cx = (sigmoid(tx) + ax) * stride;
                float cy = (sigmoid(ty) + ay) * stride;
                float bw = aw * expf(tw);
                float bh = ah * expf(th);
                float x0 = (cx - bw / 2.0f - pad_x) / scale_ratio;
                float y0 = (cy - bh / 2.0f - pad_y) / scale_ratio;
                float x1 = (cx + bw / 2.0f - pad_x) / scale_ratio;
                float y1 = (cy + bh / 2.0f - pad_y) / scale_ratio;
                x0 = fmaxf(0.f, fminf(x0, img_w));
                y0 = fmaxf(0.f, fminf(y0, img_h));
                x1 = fmaxf(0.f, fminf(x1, img_w));
                y1 = fmaxf(0.f, fminf(y1, img_h));
                if (x1 - x0 < 8.f || y1 - y0 < 8.f) continue;
                if (*n_cands >= max_cands) continue;
                cands[*n_cands].x = x0; cands[*n_cands].y = y0;
                cands[*n_cands].w = x1 - x0; cands[*n_cands].h = y1 - y0;
                cands[*n_cands].score = conf;
                (*n_cands)++;
            }
        }
    }
    return 0;
}

static int nms_person(candidate_t *c, int n, float iou_th, candidate_t *keep, int max_keep) {
    int order[NUM_CANDIDATES];
    if (n > NUM_CANDIDATES) n = NUM_CANDIDATES;
    for (int i = 0; i < n; i++) order[i] = i;
    for (int i = 0; i < n - 1; i++)
        for (int j = i + 1; j < n; j++)
            if (c[order[j]].score > c[order[i]].score) {
                int t = order[i]; order[i] = order[j]; order[j] = t;
            }
    int suppressed[NUM_CANDIDATES] = {0};
    int n_keep = 0;
    for (int i = 0; i < n; i++) {
        int a = order[i];
        if (suppressed[a]) continue;
        keep[n_keep++] = c[a];
        if (n_keep >= max_keep) break;
        for (int j = i + 1; j < n; j++) {
            int b = order[j];
            if (suppressed[b]) continue;
            float ax1 = c[a].x, ay1 = c[a].y, ax2 = c[a].x + c[a].w, ay2 = c[a].y + c[a].h;
            float bx1 = c[b].x, by1 = c[b].y, bx2 = c[b].x + c[b].w, by2 = c[b].y + c[b].h;
            float ix1 = fmaxf(ax1, bx1), iy1 = fmaxf(ay1, by1);
            float ix2 = fminf(ax2, bx2), iy2 = fminf(ay2, by2);
            float iw = fmaxf(0.f, ix2 - ix1), ih = fmaxf(0.f, iy2 - iy1);
            float inter = iw * ih;
            float uni = c[a].w * c[a].h + c[b].w * c[b].h - inter;
            if (uni > 0.f && inter / uni > iou_th) suppressed[b] = 1;
        }
    }
    return n_keep;
}

int detect_persons(hand_landmark_ctx_t *ctx,
                   const unsigned char *bgr888, int img_w, int img_h,
                   float person_boxes[], int max_persons) {
    (void)bgr888; (void)img_w; (void)img_h;

    int ret = rknn_run(ctx->detector_ctx, NULL);
    if (ret != 0) { printf("det rknn_run fail: %d\n", ret); return 0; }

    float scale_ratio = fminf((float)ctx->det_model_w / img_w, (float)ctx->det_model_h / img_h);
    int new_w = (int)(img_w * scale_ratio);
    int new_h = (int)(img_h * scale_ratio);
    float pad_x = (ctx->det_model_w - new_w) * 0.5f;
    float pad_y = (ctx->det_model_h - new_h) * 0.5f;

    candidate_t cands[NUM_CANDIDATES];
    int n = 0;

    for (int s = 0; s < 3 && s < ctx->det_io.n_output; s++) {
        int8_t *raw = (int8_t *)ctx->det_output_mems[s]->virt_addr;
        int32_t zp = ctx->det_output_attrs[s].zp;
        float sc = ctx->det_output_attrs[s].scale;
        int W = YOLOV5_GRID_SIZES[s];
        decode_one_stride(raw, zp, sc, s, W, W,
                          scale_ratio, pad_x, pad_y,
                          (float)img_w, (float)img_h,
                          0.4f, cands, NUM_CANDIDATES, &n);
    }

    candidate_t kept[8];
    int nk = nms_person(cands, n, 0.5f, kept, max_persons);
    for (int i = 0; i < nk; i++) {
        person_boxes[i*5+0] = kept[i].x;
        person_boxes[i*5+1] = kept[i].y;
        person_boxes[i*5+2] = kept[i].w;
        person_boxes[i*5+3] = kept[i].h;
        person_boxes[i*5+4] = kept[i].score;
    }
    return nk;
}

int detect_landmarks(hand_landmark_ctx_t *ctx,
                     const unsigned char *bgr888, int img_w, int img_h,
                     const float person_box[4],
                     hand_result_t *out) {
    memset(out, 0, sizeof(*out));
    out->person_box[0] = person_box[0];
    out->person_box[1] = person_box[1];
    out->person_box[2] = person_box[2];
    out->person_box[3] = person_box[3];
    (void)bgr888;

    int ret = rknn_run(ctx->landmarks_ctx, NULL);
    if (ret != 0) { printf("lm rknn_run fail: %d\n", ret); return -1; }

    int n_out = ctx->lm_io.n_output;
    int lm_idx = -1, hd_idx = -1, pr_idx = -1;
    for (int i = 0; i < n_out; i++) {
        int ne = ctx->lm_output_attrs[i].n_elems;
        if (ne == 63) lm_idx = i;
        else if (ne == 1) {
            if (hd_idx < 0) hd_idx = i;
            else if (pr_idx < 0) pr_idx = i;
        }
    }
    if (lm_idx < 0) lm_idx = 0;
    if (hd_idx < 0) hd_idx = (n_out > 1) ? 1 : 0;

    int8_t *lm_raw = (int8_t *)ctx->lm_output_mems[lm_idx]->virt_addr;
    int32_t lm_zp  = ctx->lm_output_attrs[lm_idx].zp;
    float   lm_sc  = ctx->lm_output_attrs[lm_idx].scale;

    float cx_img = person_box[0] + person_box[2] * 0.5f;
    float cy_img = person_box[1] + person_box[3] * 0.30f;
    float box_side = fmaxf(person_box[2], person_box[3] * 0.65f) * 1.2f;
    float half = box_side * 0.5f;

    float x0 = fmaxf(0.f, cx_img - half);
    float y0 = fmaxf(0.f, cy_img - half);
    float x1 = fminf((float)img_w, cx_img + half);
    float y1 = fminf((float)img_h, cy_img + half);
    out->hand_box[0] = x0; out->hand_box[1] = y0;
    out->hand_box[2] = x1 - x0; out->hand_box[3] = y1 - y0;

    float handedness = 0.5f;
    if (hd_idx >= 0 && hd_idx < n_out) {
        int8_t *hd_raw = (int8_t *)ctx->lm_output_mems[hd_idx]->virt_addr;
        int32_t hd_zp  = ctx->lm_output_attrs[hd_idx].zp;
        float   hd_sc  = ctx->lm_output_attrs[hd_idx].scale;
        handedness = sigmoid(deq(hd_raw[0], hd_zp, hd_sc));
        out->handedness_score = handedness;
    }
    if (pr_idx >= 0 && pr_idx < n_out) {
        int8_t *pr_raw = (int8_t *)ctx->lm_output_mems[pr_idx]->virt_addr;
        int32_t pr_zp  = ctx->lm_output_attrs[pr_idx].zp;
        float   pr_sc  = ctx->lm_output_attrs[pr_idx].scale;
        out->presence_score = sigmoid(deq(pr_raw[0], pr_zp, pr_sc));
    }

    float hc_x = (x0 + x1) * 0.5f;
    float hc_y = (y0 + y1) * 0.5f;
    float h_half = (x1 - x0) * 0.5f;

    for (int i = 0; i < NUM_LANDMARKS; i++) {
        float nx = deq(lm_raw[i*3+0], lm_zp, lm_sc);
        float ny = deq(lm_raw[i*3+1], lm_zp, lm_sc);
        float nz = deq(lm_raw[i*3+2], lm_zp, lm_sc);
        float img_x = hc_x + nx * h_half;
        float img_y = hc_y + ny * h_half;
        out->landmarks[i].x = img_x / (float)img_w;
        out->landmarks[i].y = img_y / (float)img_h;
        out->landmarks[i].z = nz;
    }
    out->handedness = handedness;
    return 0;
}