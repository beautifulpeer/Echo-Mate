#include "lp_value.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
static char *copy(const char *s)
{
    if (!s)
        return NULL;
    size_t n = strlen(s) + 1;
    char *p = malloc(n);
    if (p)
        memcpy(p, s, n);
    return p;
}
static lp_value_t *make(lp_value_kind_t kind)
{
    lp_value_t *v = calloc(1, sizeof(*v));
    if (v)
        v->kind = kind;
    return v;
}
lp_value_t *lp_value_map(void)
{
    return make(LP_MAP);
}
lp_value_t *lp_value_array(void)
{
    return make(LP_ARRAY);
}
lp_value_t *lp_value_null(void)
{
    return make(LP_NULL);
}
lp_value_t *lp_value_bool(bool n)
{
    lp_value_t *v = make(LP_BOOL);
    if (v)
        v->boolean = n;
    return v;
}
lp_value_t *lp_value_false(void)
{
    return lp_value_bool(false);
}
lp_value_t *lp_value_number(double n)
{
    if (!isfinite(n))
        return NULL;
    lp_value_t *v = make(LP_NUMBER);
    if (v)
        v->number = n;
    return v;
}
lp_value_t *lp_value_text(const char *s)
{
    lp_value_t *v = make(LP_TEXT);
    if (v && !(v->text = copy(s)))
    {
        free(v);
        v = NULL;
    }
    return v;
}
void lp_value_free(lp_value_t *v)
{
    while (v)
    {
        lp_value_t *next = v->next;
        lp_value_free(v->child);
        free(v->key);
        free(v->text);
        free(v);
        v = next;
    }
}
static bool append(lp_value_t *parent, lp_value_t *v)
{
    if (!parent || !v || v->next)
        return false;
    lp_value_t **tail = &parent->child;
    while (*tail)
        tail = &(*tail)->next;
    *tail = v;
    return true;
}
bool lp_value_append(lp_value_t *a, lp_value_t *v)
{
    return lp_value_is_array(a) && append(a, v);
}
lp_value_t *lp_value_get(const lp_value_t *m, const char *key)
{
    if (!lp_value_is_map(m) || !key)
        return NULL;
    for (lp_value_t *v = m->child; v; v = v->next)
        if (v->key && !strcmp(v->key, key))
            return v;
    return NULL;
}
bool lp_value_put(lp_value_t *m, const char *key, lp_value_t *v)
{
    if (!lp_value_is_map(m) || !key || !v || v->next || lp_value_get(m, key))
        return false;
    char *name = copy(key);
    if (!name)
        return false;
    free(v->key);
    v->key = name;
    return append(m, v);
}
static lp_value_t *put(lp_value_t *m, const char *key, lp_value_t *v)
{
    if (!lp_value_put(m, key, v))
    {
        lp_value_free(v);
        return NULL;
    }
    return v;
}
lp_value_t *lp_value_put_number(lp_value_t *m, const char *k, double n)
{
    return put(m, k, lp_value_number(n));
}
lp_value_t *lp_value_put_bool(lp_value_t *m, const char *k, bool n)
{
    return put(m, k, lp_value_bool(n));
}
lp_value_t *lp_value_put_text(lp_value_t *m, const char *k, const char *s)
{
    return put(m, k, lp_value_text(s));
}
lp_value_t *lp_value_put_map(lp_value_t *m, const char *k)
{
    return put(m, k, lp_value_map());
}
lp_value_t *lp_value_put_array(lp_value_t *m, const char *k)
{
    return put(m, k, lp_value_array());
}
lp_value_t *lp_value_detach(lp_value_t *m, lp_value_t *v)
{
    if (!m || !v)
        return NULL;
    lp_value_t **p = &m->child;
    while (*p && *p != v)
        p = &(*p)->next;
    if (!*p)
        return NULL;
    *p = v->next;
    v->next = NULL;
    return v;
}
bool lp_value_replace(lp_value_t *m, const char *key, lp_value_t *v)
{
    lp_value_t *old = lp_value_get(m, key);
    if (!old || !v)
        return false;
    char *name = copy(key);
    if (!name)
        return false;
    lp_value_t **p = &m->child;
    while (*p != old)
        p = &(*p)->next;
    free(v->key);
    v->key = name;
    v->next = old->next;
    *p = v;
    old->next = NULL;
    lp_value_free(old);
    return true;
}
size_t lp_value_count(const lp_value_t *v)
{
    size_t n = 0;
    if (v)
        for (const lp_value_t *p = v->child; p; p = p->next)
            n++;
    return n;
}
lp_value_t *lp_value_clone(const lp_value_t *v, bool recursive)
{
    if (!v)
        return NULL;
    lp_value_t *out = make(v->kind);
    if (!out)
        return NULL;
    out->number = v->number;
    out->boolean = v->boolean;
    if (v->text && !(out->text = copy(v->text)))
        goto fail;
    if (v->key && !(out->key = copy(v->key)))
        goto fail;
    if (recursive)
        for (const lp_value_t *p = v->child; p; p = p->next)
        {
            lp_value_t *c = lp_value_clone(p, true);
            if (!c)
                goto fail;
            append(out, c);
        }
    return out;
fail:
    lp_value_free(out);
    return NULL;
}
