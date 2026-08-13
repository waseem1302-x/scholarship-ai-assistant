"""Compromised-password screening using the Pwned Passwords k-anonymity API."""

import hashlib
from urllib.error import URLError
from urllib.request import Request, urlopen


class PasswordBreachCheckUnavailable(RuntimeError):
    """The configured breached-password service could not be reached safely."""


class PwnedPasswordsChecker:
    def __init__(self, *, endpoint: str, timeout_seconds: int) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def is_compromised(self, password: str) -> bool:
        digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]
        request = Request(
            f"{self.endpoint}/{prefix}",
            headers={"User-Agent": "ScholarshipAIAssistant/1.0"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("ascii")
        except (OSError, URLError, UnicodeDecodeError) as exc:
            raise PasswordBreachCheckUnavailable() from exc
        return any(line.partition(":")[0] == suffix for line in body.splitlines())
