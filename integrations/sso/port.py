from typing import Protocol


class SsoAuthenticationProvider(Protocol):
    def authenticate(self, credentials: dict) -> dict:
        """Return a local user id and tenant id. The auth module still issues application tokens."""
