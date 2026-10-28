/**
 * Minimal JSON for the Archipelago client: a DOM parser for the server's
 * packets and a string builder for ours. Numbers keep an exact int64 when
 * they are integral (AP item and location IDs exceed a float's precision,
 * not a double's, but integers are what the protocol means).
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { AJ_NULL, AJ_BOOL, AJ_NUM, AJ_STR, AJ_ARR, AJ_OBJ } AjType;

typedef struct AjValue AjValue;
struct AjValue {
    AjType type;
    bool b;
    double num;
    int64_t i;          /* exact when is_int */
    bool is_int;
    char *str;          /* AJ_STR: value; object member: key in `key` */
    char *key;          /* member name when this value sits in an object */
    AjValue *child;     /* first element/member */
    AjValue *next;      /* next sibling */
    size_t len;         /* element/member count */
};

/* Parses `text` (NUL-terminated). Returns NULL on malformed input. */
AjValue *aj_parse(const char *text);
void aj_free(AjValue *v);

const AjValue *aj_get(const AjValue *obj, const char *key);  /* NULL if absent */
const AjValue *aj_at(const AjValue *arr, size_t i);
const char *aj_str(const AjValue *v, const char *fallback);
int64_t aj_int(const AjValue *v, int64_t fallback);
bool aj_bool(const AjValue *v, bool fallback);

/* Growing output buffer. */
typedef struct { char *buf; size_t len, cap; bool oom; } AjBuf;
void ajb_raw(AjBuf *b, const char *s);
void ajb_fmt(AjBuf *b, const char *fmt, ...);
void ajb_str(AjBuf *b, const char *s);   /* quoted and escaped */
void ajb_free(AjBuf *b);
