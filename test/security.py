import ipaddress
import re
from typing import List, Optional
from urllib.parse import urlparse

# Private IP ranges
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]


def is_private_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        for network in PRIVATE_IP_RANGES:
            if ip_obj in network:
                return True
        return False
    except ValueError:
        return False


def compile_allowed_patterns(allowed_domains: List[str]):
    return [re.compile(pattern) for pattern in allowed_domains]


def is_domain_allowed(domain: str, allowed_patterns) -> bool:
    if not allowed_patterns:
        return True
    for pattern in allowed_patterns:
        if pattern.match(domain):
            return True
    return False


def extract_domain(url: str) -> Optional[str]:
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        parsed = urlparse(url)
        return parsed.hostname
    except Exception:
        return None
