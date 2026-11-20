#include "lp_wire.h"
#include "lp_wire_keys.h"
#include <math.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

typedef struct
{
    uint8_t kind, opcode;
    const char *name;
} message_type_t;
static const message_type_t types[] = {
    {1, 1, "telemetry"},       {1, 2, "audio"},        {1, 3, "telemetry_batch"},
    {2, 1, "status"},          {2, 2, "capabilities"}, {2, 3, "ack"},
    {3, 1, "command"},         {3, 2, "set"},          {3, 3, "capabilities_request"},
    {3, 4, "capabilities_ack"}};
typedef struct
{
    uint8_t *data;
    size_t pos, capacity;
    bool ok;
} writer_t;
static void put(writer_t *w, uint64_t n, size_t count)
{
    if (w->pos + count > LP_WIRE_MAX)
    {
        w->ok = false;
        return;
    }
    if (w->data && w->pos + count > w->capacity)
    {
        w->ok = false;
        return;
    }
    for (size_t i = 0; i < count; i++)
    {
        if (w->data)
            w->data[w->pos] = (uint8_t)(n >> (8 * i));
        w->pos++;
    }
}
static void string(writer_t *w, const char *s)
{
    size_t count = strlen(s);
    if (count > 65535)
    {
        w->ok = false;
        return;
    }
    put(w, count, 2);
    for (size_t i = 0; i < count; i++)
        put(w, (uint8_t)s[i], 1);
}
static void value(writer_t *w, const lp_value_t *v, unsigned depth, bool root)
{
    if (!v || depth > 16)
    {
        w->ok = false;
        return;
    }
    if (lp_value_is_null(v))
        put(w, 0, 1);
    else if (lp_value_is_bool(v))
        put(w, lp_value_is_true(v) ? 2 : 1, 1);
    else if (lp_value_is_number(v))
    {
        double n = v->number;
        if (!isfinite(n))
        {
            w->ok = false;
            return;
        }
        if (n == floor(n) && n >= INT32_MIN && n <= INT32_MAX)
        {
            put(w, 3, 1);
            put(w, (uint32_t)(int32_t)n, 4);
        }
        else if (n == floor(n) && n >= 0 && n <= UINT32_MAX)
        {
            put(w, 4, 1);
            put(w, (uint32_t)n, 4);
        }
        else
        {
            uint64_t bits;
            memcpy(&bits, &n, 8);
            put(w, 5, 1);
            put(w, bits, 8);
        }
    }
    else if (lp_value_is_text(v))
    {
        put(w, 6, 1);
        string(w, v->text);
    }
    else if (lp_value_is_array(v) || lp_value_is_map(v))
    {
        bool object = lp_value_is_map(v);
        size_t count = 0;
        const lp_value_t *item;
        LP_VALUE_EACH(item, v)
        {
            if (root && (!strcmp(item->key, "v") || !strcmp(item->key, "type")))
                continue;
            count++;
        }
        if (count > 4096)
        {
            w->ok = false;
            return;
        }
        put(w, object ? 8 : 7, 1);
        put(w, count, 2);
        LP_VALUE_EACH(item, v)
        {
            if (root && (!strcmp(item->key, "v") || !strcmp(item->key, "type")))
                continue;
            if (object)
            {
                size_t id = 0;
                for (size_t i = 0; i < sizeof(lp_wire_keys) / sizeof(*lp_wire_keys); i++)
                    if (!strcmp(item->key, lp_wire_keys[i]))
                    {
                        id = i + 1;
                        break;
                    }
                put(w, id, 1);
                if (!id)
                    string(w, item->key);
            }
            value(w, item, depth + 1, false);
        }
    }
    else
        w->ok = false;
}
static uint16_t crc16(const uint8_t *p, size_t count)
{
    uint16_t crc = 0xffff;
    for (size_t i = 0; i < count; i++)
    {
        crc ^= (uint16_t)p[i] << 8;
        for (int b = 0; b < 8; b++)
            crc = (crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0);
    }
    return crc;
}
uint8_t *lp_wire_encode(const lp_value_t *message, size_t *length)
{
    const lp_value_t *type = lp_value_get(message, "type"), *v = lp_value_get(message, "v");
    if (!lp_value_is_text(type) || !lp_value_is_number(v) || v->number != 1)
        return NULL;
    const message_type_t *t = NULL;
    for (size_t i = 0; i < sizeof(types) / sizeof(*types); i++)
        if (!strcmp(type->text, types[i].name))
        {
            t = &types[i];
            break;
        }
    if (!t)
        return NULL;
    writer_t measure = {.pos = 9, .ok = true};
    value(&measure, message, 0, true);
    if (!measure.ok || measure.pos > 65543)
        return NULL;
    size_t size = measure.pos + 2;
    uint8_t *data = malloc(size);
    if (!data)
        return NULL;
    writer_t w = {.data = data, .capacity = size, .ok = true};
    put(&w, 0x5aa5, 2);
    put(&w, 1, 1);
    put(&w, t->kind, 1);
    put(&w, size - 10, 4);
    put(&w, t->opcode, 1);
    value(&w, message, 0, true);
    if (!w.ok)
    {
        free(data);
        return NULL;
    }
    put(&w, crc16(data, size - 2), 2);
    if (!w.ok)
    {
        free(data);
        return NULL;
    }
    *length = size;
    return data;
}
typedef struct
{
    const uint8_t *data;
    size_t pos, end;
    bool ok;
} reader_t;
static uint64_t take(reader_t *r, size_t count)
{
    if (r->pos + count > r->end)
    {
        r->ok = false;
        return 0;
    }
    uint64_t n = 0;
    for (size_t i = 0; i < count; i++)
        n |= (uint64_t)r->data[r->pos++] << (8 * i);
    return n;
}
static char *read_string(reader_t *r)
{
    size_t count = take(r, 2);
    if (!r->ok || r->pos + count > r->end)
    {
        r->ok = false;
        return NULL;
    }
    char *s = malloc(count + 1);
    if (!s)
    {
        r->ok = false;
        return NULL;
    }
    memcpy(s, r->data + r->pos, count);
    s[count] = 0;
    r->pos += count;
    if (memchr(s, 0, count))
    {
        free(s);
        r->ok = false;
        return NULL;
    }
    return s;
}
static lp_value_t *read_value(reader_t *r, unsigned depth)
{
    if (depth > 16 || !r->ok)
    {
        r->ok = false;
        return NULL;
    }
    unsigned tag = take(r, 1);
    lp_value_t *v = NULL;
    if (tag == 0)
        v = lp_value_null();
    else if (tag < 3)
        v = lp_value_bool(tag == 2);
    else if (tag <= 5)
    {
        uint64_t bits = take(r, tag == 5 ? 8 : 4);
        double n;
        if (tag == 5)
            memcpy(&n, &bits, 8);
        else
            n = tag == 3 ? (double)(int32_t)(uint32_t)bits : (double)(uint32_t)bits;
        if (!isfinite(n))
            r->ok = false;
        else
            v = lp_value_number(n);
    }
    else if (tag == 6)
    {
        char *s = read_string(r);
        if (s)
        {
            v = lp_value_text(s);
            free(s);
        }
    }
    else if (tag == 7 || tag == 8)
    {
        size_t count = take(r, 2);
        if (count > 4096)
        {
            r->ok = false;
            return NULL;
        }
        v = tag == 7 ? lp_value_array() : lp_value_map();
        if (!v)
        {
            r->ok = false;
            return NULL;
        }
        for (size_t i = 0; i < count && r->ok; i++)
        {
            char *owned = NULL;
            const char *key = NULL;
            if (tag == 8)
            {
                unsigned id = take(r, 1);
                if (id > sizeof(lp_wire_keys) / sizeof(*lp_wire_keys))
                {
                    r->ok = false;
                    break;
                }
                key = id ? lp_wire_keys[id - 1] : (owned = read_string(r));
                if (!key || lp_value_get(v, key) || !strcmp(key, "__proto__") ||
                    !strcmp(key, "constructor") || !strcmp(key, "prototype"))
                {
                    free(owned);
                    r->ok = false;
                    break;
                }
            }
            lp_value_t *item = read_value(r, depth + 1);
            if (!item)
            {
                free(owned);
                r->ok = false;
                break;
            }
            bool added = tag == 8 ? lp_value_put(v, key, item) : lp_value_append(v, item);
            free(owned);
            if (!added)
            {
                lp_value_free(item);
                r->ok = false;
            }
        }
    }
    else
        r->ok = false;
    if (!v)
        r->ok = false;
    if (!r->ok)
    {
        lp_value_free(v);
        return NULL;
    }
    return v;
}
int lp_wire_frame_size(const uint8_t *data, size_t used, size_t *length)
{
    if (used < 2)
        return 0;
    if (data[0] != 0xa5 || data[1] != 0x5a)
        return -1;
    if (used < 8)
        return 0;
    uint32_t n = (uint32_t)data[4] | (uint32_t)data[5] << 8 | (uint32_t)data[6] << 16 |
                 (uint32_t)data[7] << 24;
    if (data[2] != 1 || data[3] < 1 || data[3] > 3 || n < 2 || n > 65535)
        return -1;
    *length = n + 10;
    if (used < *length)
    {
        for (size_t i = 1; i + 12 <= used; ++i)
        {
            if (data[i] != 0xa5 || data[i + 1] != 0x5a || data[i + 2] != 1 || data[i + 3] < 1 ||
                data[i + 3] > 3)
                continue;
            uint32_t size = (uint32_t)data[i + 4] | (uint32_t)data[i + 5] << 8 |
                            (uint32_t)data[i + 6] << 16 | (uint32_t)data[i + 7] << 24;
            if (size < 2 || size > 65535 || i + size + 10 > used)
                continue;
            size_t end = i + size + 10;
            if (crc16(data + i, size + 8) == (uint16_t)(data[end - 2] | data[end - 1] << 8))
                return -1;
        }
    }
    return used >= *length ? 1 : 0;
}
lp_value_t *lp_wire_decode(const uint8_t *frame, size_t length)
{
    size_t expected;
    if (lp_wire_frame_size(frame, length, &expected) != 1 || expected != length ||
        crc16(frame, length - 2) != (uint16_t)(frame[length - 2] | frame[length - 1] << 8))
        return NULL;
    const char *name = NULL;
    for (size_t i = 0; i < sizeof(types) / sizeof(*types); i++)
        if (types[i].kind == frame[3] && types[i].opcode == frame[8])
        {
            name = types[i].name;
            break;
        }
    if (!name)
        return NULL;
    reader_t r = {.data = frame, .pos = 9, .end = length - 2, .ok = true};
    lp_value_t *root = read_value(&r, 0);
    if (!r.ok || r.pos != r.end || !lp_value_is_map(root) || lp_value_get(root, "v") ||
        lp_value_get(root, "type"))
    {
        lp_value_free(root);
        return NULL;
    }
    if (!lp_value_put_number(root, "v", 1) || !lp_value_put_text(root, "type", name))
    {
        lp_value_free(root);
        return NULL;
    }
    return root;
}
