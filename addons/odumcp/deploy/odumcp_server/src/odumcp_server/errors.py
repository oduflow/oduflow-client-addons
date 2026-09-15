from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class OduMcpError(Exception):
    """Base exception safe to translate to an MCP tool error."""


@dataclass(slots=True)
class OdooApiError(OduMcpError):
    code: str
    message: str
    retryable: bool = False
    status_code: int | None = None
    request_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        # Подробности отказа попадают в текст: клиент видит только строку
        # ToolError и по ней решает, что исправить в следующем вызове.
        if not self.data:
            return f"{self.code}: {self.message}"
        details = json.dumps(self.data, ensure_ascii=False, sort_keys=True)
        return f"{self.code}: {self.message} details={details}"

    def as_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.data:
            error["data"] = self.data
        return {
            "ok": False,
            "request_id": self.request_id,
            "error": error,
        }


class ConfigurationError(OduMcpError):
    """Configuration is incomplete or unsafe."""


class ResponseTooLargeError(OdooApiError):
    def __init__(self, *, max_bytes: int, request_id: str | None = None):
        super().__init__(
            code="response_too_large",
            message=f"Odoo response exceeded the configured {max_bytes}-byte limit.",
            retryable=False,
            status_code=413,
            request_id=request_id,
        )


class CircuitOpenError(OdooApiError):
    def __init__(self):
        super().__init__(
            code="connector_unavailable",
            message="Odoo connector circuit is open after repeated transport failures.",
            retryable=True,
            status_code=503,
        )
