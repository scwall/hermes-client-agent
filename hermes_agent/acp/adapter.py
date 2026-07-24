"""Base class for ACP agent adapters."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

_log = logging.getLogger("hermes-agent")


class AcpAdapter(ABC):
    name = "generic"

    @abstractmethod
    def detect_binary(self) -> Optional[str]: ...

    @abstractmethod
    def spawn(self, port: int) -> int: ...

    @abstractmethod
    def health_check(self, endpoint: str) -> bool: ...

    @abstractmethod
    def create_session(self, endpoint: str) -> dict: ...

    @abstractmethod
    def send_message(self, endpoint: str, session_id: str, prompt: str, model: str, timeout: int) -> dict: ...

    @abstractmethod
    def cancel(self, endpoint: str, session_id: str) -> None: ...

    @abstractmethod
    def get_default_port(self) -> int: ...
