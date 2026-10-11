import socket

from lamarck.net import prefer_ipv4

V6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 443, 0, 0))
V4 = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))


def test_ipv4_addresses_come_first_and_ipv6_stays_as_fallback():
    wrapped = prefer_ipv4(lambda *a, **k: [V6, V4, V6])
    assert wrapped("example.com", 443) == [V4, V6, V6]


def test_wrapping_twice_is_harmless():
    once = prefer_ipv4(lambda *a, **k: [V6, V4])
    assert prefer_ipv4(once) is once
