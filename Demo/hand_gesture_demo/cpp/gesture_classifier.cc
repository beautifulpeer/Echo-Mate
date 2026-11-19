// Port of /home/lubancat/lzd/hand_gesture/src/gesture_classifier.py
// Rule-based static gesture classifier on 21 normalized hand landmarks.

#include <string.h>
#include <stdio.h>
#include <math.h>

#include "gesture_classifier.h"

// MediaPipe hand landmark indices
#define LM_WRIST      0
#define LM_THUMB_CMC  1
#define LM_THUMB_MCP  2
#define LM_THUMB_IP   3
#define LM_THUMB_TIP  4
#define LM_INDEX_MCP  5
#define LM_INDEX_PIP  6
#define LM_INDEX_DIP  7
#define LM_INDEX_TIP  8
#define LM_MIDDLE_MCP 9
#define LM_MIDDLE_PIP 10
#define LM_MIDDLE_DIP 11
#define LM_MIDDLE_TIP 12
#define LM_RING_MCP   13
#define LM_RING_PIP   14
#define LM_RING_DIP   15
#define LM_RING_TIP   16
#define LM_PINKY_MCP  17
#define LM_PINKY_PIP  18
#define LM_PINKY_DIP  19
#define LM_PINKY_TIP  20

static const char *GESTURE_NAMES[GESTURE_COUNT_MAX] = {
    "Unknown",
    "Fist",
    "Open Palm",
    "Thumb Up",
    "Thumb Down",
    "Index Point",
    "Victory",
    "OK",
    "I Love You",
    "Pinky"
};

static inline float dist2(const landmark_t *a, const landmark_t *b) {
    float dx = a->x - b->x, dy = a->y - b->y;
    return dx * dx + dy * dy;
}

// Reference distance: wrist (0) -> middle MCP (9). Normalizes "spread".
static inline float hand_scale(const landmark_t *lm) {
    return sqrtf(dist2(&lm[LM_WRIST], &lm[LM_MIDDLE_MCP])) + 1e-6f;
}

// Finger is extended if TIP is far from MCP (> threshold * scale).
static inline int finger_extended(const landmark_t *lm, int tip_idx, int mcp_idx,
                                  float th_ratio) {
    float scale = hand_scale(lm);
    float d = sqrtf(dist2(&lm[tip_idx], &lm[mcp_idx]));
    return (d / scale) > th_ratio;
}

// Thumb is special: compare tip to IP (knuckle) and to index MCP.
static inline int thumb_extended(const landmark_t *lm, float th_ratio) {
    float scale = hand_scale(lm);
    // 2D direction in image: x grows to right (mirrored display).
    // We just use distance thumb TIP vs INDEX_MCP as a coarse test.
    float d = sqrtf(dist2(&lm[LM_THUMB_TIP], &lm[LM_INDEX_MCP]));
    return (d / scale) > th_ratio;
}

int classify_gesture(const landmark_t *lm, int num_lm, float handedness,
                     char *name_out, int name_buf_size) {
    if (num_lm != NUM_LANDMARKS) {
        if (name_out && name_buf_size > 0) {
            snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_UNKNOWN]);
        }
        return GESTURE_UNKNOWN;
    }

    int idx_ext = finger_extended(lm, LM_INDEX_TIP,  LM_INDEX_MCP,  0.55f);
    int mid_ext = finger_extended(lm, LM_MIDDLE_TIP, LM_MIDDLE_MCP, 0.55f);
    int rng_ext = finger_extended(lm, LM_RING_TIP,   LM_RING_MCP,   0.55f);
    int pnk_ext = finger_extended(lm, LM_PINKY_TIP,  LM_PINKY_MCP,  0.55f);
    int thb_ext = thumb_extended(lm, 0.55f);

    // Open palm: all 5 fingers extended
    if (idx_ext && mid_ext && rng_ext && pnk_ext && thb_ext) {
        if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_OPEN_PALM]);
        return GESTURE_OPEN_PALM;
    }

    // Fist: all folded
    if (!idx_ext && !mid_ext && !rng_ext && !pnk_ext) {
        if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_FIST]);
        return GESTURE_FIST;
    }

    // Victory: index + middle extended, others curled
    if (idx_ext && mid_ext && !rng_ext && !pnk_ext) {
        if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_VICTORY]);
        return GESTURE_VICTORY;
    }

    // Index point: only index extended
    if (idx_ext && !mid_ext && !rng_ext && !pnk_ext) {
        if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_INDEX_POINT]);
        return GESTURE_INDEX_POINT;
    }

    // Pinky: only pinky extended
    if (!idx_ext && !mid_ext && !rng_ext && pnk_ext) {
        if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_PINKY]);
        return GESTURE_PINKY;
    }

    // I love you: thumb + index + pinky extended, middle + ring curled
    if (thb_ext && idx_ext && !mid_ext && !rng_ext && pnk_ext) {
        if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_LOVE]);
        return GESTURE_LOVE;
    }

    // Thumb up / down: only thumb extended, others curled
    if (thb_ext && !idx_ext && !mid_ext && !rng_ext && !pnk_ext) {
        // Compare thumb TIP y vs wrist y. Note: in normalized image coords y grows downward.
        // "Up" => tip_y < wrist_y, "Down" => tip_y > wrist_y.
        float dy = lm[LM_THUMB_TIP].y - lm[LM_WRIST].y;
        gesture_id_t id = (dy < 0.0f) ? GESTURE_THUMB_UP : GESTURE_THUMB_DOWN;
        if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[id]);
        return id;
    }

    // OK: thumb tip close to index tip, others extended (rough heuristic).
    {
        float scale = hand_scale(lm);
        float d_th_idx = sqrtf(dist2(&lm[LM_THUMB_TIP], &lm[LM_INDEX_TIP]));
        if ((d_th_idx / scale) < 0.30f && mid_ext && rng_ext && pnk_ext) {
            if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_OK]);
            return GESTURE_OK;
        }
    }

    if (name_out && name_buf_size > 0) snprintf(name_out, name_buf_size, "%s", GESTURE_NAMES[GESTURE_UNKNOWN]);
    return GESTURE_UNKNOWN;
}