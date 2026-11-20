#pragma once
#include <stdbool.h>
#include <stddef.h>

/* Native typed binary fields; deliberately no JSON parser or text serializer. */
typedef enum
{
    LP_NULL,
    LP_BOOL,
    LP_NUMBER,
    LP_TEXT,
    LP_ARRAY,
    LP_MAP
} lp_value_kind_t;
typedef struct lp_value
{
    lp_value_kind_t kind;
    struct lp_value *next, *child;
    char *key, *text;
    double number;
    bool boolean;
} lp_value_t;
lp_value_t *lp_value_map(void);
lp_value_t *lp_value_array(void);
lp_value_t *lp_value_null(void);
lp_value_t *lp_value_bool(bool value);
lp_value_t *lp_value_false(void);
lp_value_t *lp_value_number(double value);
lp_value_t *lp_value_text(const char *value);
void lp_value_free(lp_value_t *value);
bool lp_value_append(lp_value_t *array, lp_value_t *value);
bool lp_value_put(lp_value_t *map, const char *key, lp_value_t *value);
lp_value_t *lp_value_get(const lp_value_t *map, const char *key);
lp_value_t *lp_value_put_number(lp_value_t *map, const char *key, double value);
lp_value_t *lp_value_put_bool(lp_value_t *map, const char *key, bool value);
lp_value_t *lp_value_put_text(lp_value_t *map, const char *key, const char *value);
lp_value_t *lp_value_put_map(lp_value_t *map, const char *key);
lp_value_t *lp_value_put_array(lp_value_t *map, const char *key);
lp_value_t *lp_value_clone(const lp_value_t *value, bool recursive);
lp_value_t *lp_value_detach(lp_value_t *map, lp_value_t *value);
bool lp_value_replace(lp_value_t *map, const char *key, lp_value_t *value);
size_t lp_value_count(const lp_value_t *value);
static inline bool lp_value_is_map(const lp_value_t *v)
{
    return v && v->kind == LP_MAP;
}
static inline bool lp_value_is_array(const lp_value_t *v)
{
    return v && v->kind == LP_ARRAY;
}
static inline bool lp_value_is_null(const lp_value_t *v)
{
    return v && v->kind == LP_NULL;
}
static inline bool lp_value_is_bool(const lp_value_t *v)
{
    return v && v->kind == LP_BOOL;
}
static inline bool lp_value_is_number(const lp_value_t *v)
{
    return v && v->kind == LP_NUMBER;
}
static inline bool lp_value_is_text(const lp_value_t *v)
{
    return v && v->kind == LP_TEXT;
}
static inline bool lp_value_is_true(const lp_value_t *v)
{
    return lp_value_is_bool(v) && v->boolean;
}
#define LP_VALUE_EACH(item, parent)                                                                \
    for ((item) = (parent) ? (parent)->child : NULL; (item); (item) = (item)->next)
