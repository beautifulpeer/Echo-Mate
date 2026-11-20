#pragma once
#include <stddef.h>
#include <stdint.h>
#include "lp_value.h"
#define LP_WIRE_MAX 65545
/* Returned allocations belong to the caller. Decoder never accepts JSON text. */
uint8_t *lp_wire_encode(const lp_value_t *message, size_t *length);
lp_value_t *lp_wire_decode(const uint8_t *frame, size_t length);
/* Stream parser: 1 complete frame, 0 incomplete, -1 invalid (discard one byte). */
int lp_wire_frame_size(const uint8_t *data, size_t used, size_t *length);
