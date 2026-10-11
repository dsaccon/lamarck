"""Prefer IPv4 when resolving hosts.

Some networks advertise IPv6 without routing it; Python's HTTP stack then tries the IPv6 address first
and stalls. Ordering IPv4 results first keeps IPv6 as a fallback. Set LAMARCK_PREFER_IPV4=0 to disable.
"""
import os
import socket


def prefer_ipv4(getaddrinfo):
    if getattr(getaddrinfo, "_prefers_ipv4", False):
        return getaddrinfo

    def wrapped(*args, **kwargs):
        return sorted(getaddrinfo(*args, **kwargs), key=lambda info: info[0] != socket.AF_INET)

    wrapped._prefers_ipv4 = True
    return wrapped


def install() -> None:
    if os.environ.get("LAMARCK_PREFER_IPV4", "1") != "0":
        socket.getaddrinfo = prefer_ipv4(socket.getaddrinfo)
