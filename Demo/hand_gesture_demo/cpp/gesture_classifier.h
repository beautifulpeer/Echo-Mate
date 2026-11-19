#ifndef _GESTURE_CLASSIFIER_H_
#define _GESTURE_CLASSIFIER_H_

#include "hand_landmark.h"

// Returns one of the gesture label indices below.
typedef enum {
    GESTURE_UNKNOWN = 0,
    GESTURE_FIST,
    GESTURE_OPEN_PALM,
    GESTURE_THUMB_UP,
    GESTURE_THUMB_DOWN,
    GESTURE_INDEX_POINT,
    GESTURE_VICTORY,
    GESTURE_OK,
    GESTURE_LOVE,
    GESTURE_PINKY,
    GESTURE_COUNT_MAX
} gesture_id_t;

// Classify gesture from 21 hand landmarks.
// handedness is 0.0 (Left) ~ 1.0 (Right).
// Returns id and copies a short label into name_out (up to GESTURE_NAME_MAX bytes).
int classify_gesture(const landmark_t *lm, int num_lm, float handedness,
                     char *name_out, int name_buf_size);

#endif