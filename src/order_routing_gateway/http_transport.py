from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class UrllibHttpTransport:
    """Transporte HTTP basado en stdlib con manejo explícito de errores de red."""

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def send(
        self,
        method: str,
        url: str,
        payload: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **headers}
        request = urllib.request.Request(
            url=url,
            data=body,
            headers=request_headers,
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "http error status=%s url=%s body=%s",
                exc.code,
                url,
                error_body,
            )
            parsed = _safe_json_load(error_body)
            if parsed is not None:
                return parsed
            return {"error": error_body, "status_code": exc.code}
        except urllib.error.URLError as exc:
            logger.error("network error url=%s reason=%s", url, exc.reason)
            raise ConnectionError(f"failed to reach {url}: {exc.reason}") from exc

        parsed_response = _safe_json_load(raw)
        if parsed_response is None:
            raise ValueError("exchange response is not valid json")
        return parsed_response


class MockHttpTransport:
    """Transporte en memoria para pruebas y dry-runs."""

    def __init__(self, responses: dict[str, dict[str, object]] | None = None) -> None:
        self._responses = responses or {}
        self.sent_requests: list[dict[str, Any]] = []

    def send(
        self,
        method: str,
        url: str,
        payload: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, object]:
        self.sent_requests.append(
            {
                "method": method,
                "url": url,
                "payload": dict(payload),
                "headers": dict(headers),
            }
        )
        client_order_id = payload.get("newClientOrderId") or payload.get("client_order_id", "")
        if client_order_id in self._responses:
            return self._responses[client_order_id]
        return {
            "orderId": f"mock-{client_order_id}",
            "status": "FILLED",
            "executedQty": payload.get("quantity", "0"),
            "cummulativeQuoteQty": "0",
        }


def _safe_json_load(raw: str) -> dict[str, object] | None:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None
