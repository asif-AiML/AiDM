"""Validated SOCKS endpoint, explicit persistence, and session-only enablement."""

from dataclasses import dataclass
from ipaddress import ip_address
import re


@dataclass(frozen=True)
class ProxyEndpoint:
    host: str
    port: int

    def __post_init__(self):
        host = self.host.strip() if isinstance(self.host, str) else ""
        if not host or any(char in host for char in "/\\@?#%"):
            raise ValueError("Enter a plain SOCKS hostname or IP address.")
        if host.startswith("[") and host.endswith("]") and ":" in host:
            host = host[1:-1]
        try:
            host = str(ip_address(host))
        except ValueError:
            if (len(host) > 253 or not all(re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label
                    ) for label in host.removesuffix(".").split("."))
                    or re.fullmatch(r"[0-9.]+", host)):
                raise ValueError("Enter a plain SOCKS hostname or IP address.") from None
        port = str(self.port).strip()
        if not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
            raise ValueError("Enter a SOCKS port from 1 to 65535.")
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", int(port))

    @property
    def url(self):
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"socks5h://{host}:{self.port}"


class ProxySettings:
    """One shared state. Only a successful explicit save replaces the endpoint.

    The optional change callback lets the owning window refresh both views;
    neither the job model nor CLI needs Qt imports or live settings access.
    """

    KEY = "proxy/endpoint"

    def __init__(self, settings, *, on_change=None):
        self._settings = settings
        self.on_change = on_change
        self._endpoint = None
        self._enabled = False
        stored = settings.value(self.KEY)
        if isinstance(stored, (list, tuple)) and len(stored) == 2:
            try:
                self._endpoint = ProxyEndpoint(*stored)
            except ValueError:
                pass  # Invalid stored input never activates a proxy.

    @property
    def endpoint(self):
        return self._endpoint

    @property
    def enabled(self):
        return self._enabled

    @property
    def snapshot(self):
        return self._endpoint if self._enabled else None

    def save(self, host, port):
        endpoint = ProxyEndpoint(host, port)
        previous = self._settings.value(self.KEY)
        self._settings.setValue(self.KEY, [endpoint.host, str(endpoint.port)])
        self._settings.sync()
        if self._settings.status() != self._settings.Status.NoError:
            # Restore QSettings' in-memory value too, so a later flush cannot
            # silently commit the endpoint reported as unsuccessful.
            if previous is None:
                self._settings.remove(self.KEY)
            else:
                self._settings.setValue(self.KEY, previous)
            raise OSError("Could not save the SOCKS endpoint. Please try again.")
        self._endpoint = endpoint
        self._notify()

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Proxy Mode must be ON or OFF.")
        if enabled and self._endpoint is None:
            raise ValueError("Enter and save a SOCKS host and port first.")
        if enabled != self._enabled:
            self._enabled = enabled
            self._notify()

    def _notify(self):
        if self.on_change is not None:
            self.on_change()
