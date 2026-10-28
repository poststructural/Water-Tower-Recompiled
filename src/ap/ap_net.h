/**
 * Archipelago connection thread. It owns the socket, reconnects with backoff,
 * answers RoomInfo with the Connect packet it was given, and hands every
 * packet to the game thread as text. It never touches guest memory.
 *
 * Each connection gets a new generation; a send names the generation it was
 * built for and is dropped once that connection is gone, so a reply meant for
 * an old socket never reaches a new session.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { ANI_NET_PACKET, ANI_NET_UP, ANI_NET_DOWN } AniNetKind;

typedef struct {
    AniNetKind kind;
    uint64_t generation;
    char *text;            /* PACKET: one server message (a JSON array); DOWN: reason */
} AniNetEvent;

/* address: "host[:port]", "ws://host[:port]" or "wss://host[:port]". Without a
 * scheme wss is tried first, then ws, as Archipelago's own clients do.
 * connect_cmd: the JSON object of our Connect command, sent on every RoomInfo. */
void ani_net_start(const char *address, const char *connect_cmd);
void ani_net_stop(void);
/* Waits for the first RoomInfo; copies its seed_name. false on timeout. */
bool ani_net_wait_seed(int timeout_ms, char *seed, size_t n);
/* Takes up to max queued events; free each text with free(). */
size_t ani_net_drain(AniNetEvent *out, size_t max);
/* Queues a JSON array of commands for that generation's socket. */
void ani_net_send(uint64_t generation, const char *json);
