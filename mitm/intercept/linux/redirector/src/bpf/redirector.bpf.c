// SPDX-License-Identifier: GPL-2.0
// CO-RE BPF program: redirect target process sockets to TUN device.
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

// Map: target interface index (written by userspace)
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, __u32);
} tun_ifindex SEC(".maps");

// Map: target process name (written by userspace, 16 bytes max = TASK_COMM_LEN)
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, char[16]);
} target_comm SEC(".maps");

// Map: sk_storage for original destination (per-socket)
struct orig_dst {
    __u32 ip4;
    __u32 port;
};

struct {
    __uint(type, BPF_MAP_TYPE_SK_STORAGE);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, int);
    __type(value, struct orig_dst);
} sk_orig_dst SEC(".maps");

SEC("cgroup/sock_create")
int redirect_sock(struct bpf_sock *sk)
{
    // Only intercept IPv4/IPv6 TCP
    if (sk->protocol != IPPROTO_TCP)
        return 1;

    // Check if current task matches target
    __u32 key = 0;
    char *target = bpf_map_lookup_elem(&target_comm, &key);
    if (!target)
        return 1;

    char comm[16] = {};
    bpf_get_current_comm(comm, sizeof(comm));

    // Compare first 16 chars
    for (int i = 0; i < 16; i++) {
        if (comm[i] != target[i])
            return 1;
        if (comm[i] == '\0')
            break;
    }

    // Redirect to TUN interface
    __u32 *ifindex = bpf_map_lookup_elem(&tun_ifindex, &key);
    if (!ifindex)
        return 1;

    sk->bound_dev_if = *ifindex;
    return 1;
}

char LICENSE[] SEC("license") = "GPL";
