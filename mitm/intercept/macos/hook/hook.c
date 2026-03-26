#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

static __thread struct sockaddr_storage _orig_dst;
static __thread socklen_t _orig_dst_len = 0;

static int (*real_connect)(int, const struct sockaddr *, socklen_t) = NULL;

__attribute__((constructor))
static void init_hook(void) {
    real_connect = dlsym(RTLD_NEXT, "connect");
    // Signal to parent that hook is loaded
    setenv("MITM_HOOK_LOADED", "1", 1);
}

static int get_proxy_port(void) {
    const char *port_str = getenv("MITM_LOCAL_PORT");
    if (!port_str) return 8888;
    return atoi(port_str);
}

static void send_synthetic_connect(int sockfd, const char *host, int port, int tls) {
    char header[512];
    if (tls) {
        snprintf(header, sizeof(header),
            "CONNECT %s:%d HTTP/1.1\r\nX-Mitm-Transparent: 1\r\nX-Mitm-TLS: 1\r\n\r\n",
            host, port);
    } else {
        snprintf(header, sizeof(header),
            "CONNECT %s:%d HTTP/1.1\r\nX-Mitm-Transparent: 1\r\n\r\n",
            host, port);
    }
    send(sockfd, header, strlen(header), 0);
}

int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    if (!real_connect) {
        real_connect = dlsym(RTLD_NEXT, "connect");
    }

    // Only intercept IPv4/IPv6 TCP sockets
    if (addr->sa_family != AF_INET && addr->sa_family != AF_INET6) {
        return real_connect(sockfd, addr, addrlen);
    }

    // Save original destination
    memcpy(&_orig_dst, addr, addrlen);
    _orig_dst_len = addrlen;

    // Extract original host and port
    char orig_host[INET6_ADDRSTRLEN] = {0};
    int orig_port = 0;

    if (addr->sa_family == AF_INET) {
        const struct sockaddr_in *in4 = (const struct sockaddr_in *)addr;
        inet_ntop(AF_INET, &in4->sin_addr, orig_host, sizeof(orig_host));
        orig_port = ntohs(in4->sin_port);
    } else {
        const struct sockaddr_in6 *in6 = (const struct sockaddr_in6 *)addr;
        inet_ntop(AF_INET6, &in6->sin6_addr, orig_host, sizeof(orig_host));
        orig_port = ntohs(in6->sin6_port);
    }

    // Don't intercept connections to 127.0.0.1 (avoid intercepting proxy itself)
    if (strcmp(orig_host, "127.0.0.1") == 0 || strcmp(orig_host, "::1") == 0) {
        return real_connect(sockfd, addr, addrlen);
    }

    // Redirect to proxy
    int proxy_port = get_proxy_port();
    struct sockaddr_in proxy_addr = {0};
    proxy_addr.sin_family = AF_INET;
    proxy_addr.sin_port = htons(proxy_port);
    inet_pton(AF_INET, "127.0.0.1", &proxy_addr.sin_addr);

    int ret = real_connect(sockfd, (struct sockaddr *)&proxy_addr, sizeof(proxy_addr));
    if (ret != 0) {
        return ret;
    }

    // Send synthetic CONNECT header to tell proxy the real destination
    int tls = (orig_port == 443 || orig_port == 8443);
    send_synthetic_connect(sockfd, orig_host, orig_port, tls);

    return 0;
}
