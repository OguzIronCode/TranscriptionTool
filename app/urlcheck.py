"""İndirilecek URL'lerin güvenlik kontrolü (SSRF'e karşı)."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrl(ValueError):
    """Kullanıcıya gösterilebilecek, Türkçe hata mesajı taşır."""


def _is_public(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    return not allowed or any(host == a or host.endswith("." + a) for a in allowed)


def _resolve(host: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror:
        raise UnsafeUrl("Adres çözümlenemedi. URL'yi kontrol edin.")


async def validate_public_url(url: str, allowed_hosts: tuple[str, ...] = ()) -> str:
    """URL güvenliyse temizlenmiş halini döndürür, değilse UnsafeUrl fırlatır."""
    url = (url or "").strip()
    if len(url) > 2000:
        raise UnsafeUrl("URL çok uzun.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise UnsafeUrl("Geçersiz URL.")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeUrl("Yalnızca http:// veya https:// adresleri desteklenir.")
    if parts.username or parts.password:
        raise UnsafeUrl("Kullanıcı adı/şifre içeren URL'ler desteklenmez.")
    if port not in (None, 80, 443):
        raise UnsafeUrl("Yalnızca 80 ve 443 portları desteklenir.")

    host = parts.hostname.lower().rstrip(".")
    if not _host_allowed(host, allowed_hosts):
        raise UnsafeUrl("Bu sitedeki bağlantılara izin verilmiyor.")

    try:                                   # doğrudan IP adresi verilmiş olabilir
        addrs = [ipaddress.ip_address(host)]
    except ValueError:
        loop = asyncio.get_running_loop()
        addrs = [ipaddress.ip_address(a.split("%")[0]) for a in await loop.run_in_executor(None, _resolve, host)]

    if not addrs or not all(_is_public(a) for a in addrs):
        raise UnsafeUrl("Bu adrese erişime izin verilmiyor.")
    return url
