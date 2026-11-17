"""Signed Binance Spot REST client, pointed at the **testnet** by default.

* Credentials come only from environment variables (``BINANCE_TESTNET_API_KEY`` /
  ``BINANCE_TESTNET_API_SECRET``); they are never accepted on the command line, never logged and
  masked in ``repr``.
* Every signed request carries ``timestamp`` + ``recvWindow`` and an HMAC-SHA256 ``signature``
  of the query string, as Binance requires; parameters travel in the query string.
* Failures are typed: ``BinanceApiError`` is a definite answer from the exchange (e.g. rejected),
  ``ExchangeUnavailableError`` means the outcome is **unknown** (timeout, connection reset, 5xx).
  After an unknown outcome the caller must look the order up by ``newClientOrderId`` before doing
  anything else, never resend it blindly.
* The mainnet URL is only reachable through ``real_money_endpoint()``, which refuses unless the
  operator set ``ORDER_ROUTING_ALLOW_REAL_MONEY`` to the exact acknowledgement phrase.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)

TESTNET_URL = "https://testnet.binance.vision"
MAINNET_URL = "https://api.binance.com"
REAL_MONEY_ENV = "ORDER_ROUTING_ALLOW_REAL_MONEY"
REAL_MONEY_PHRASE = "I_UNDERSTAND_THIS_USES_REAL_MONEY"


class BinanceApiError(Exception):
    """The exchange answered and refused (4xx with a Binance error code)."""

    def __init__(self, status: int, code: int | None, message: str) -> None:
        super().__init__(f"binance error status={status} code={code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class ExchangeUnavailableError(ConnectionError):
    """No definite answer: timeout, network failure or 5xx. The order state is unknown."""


class RealMoneyLockedError(PermissionError):
    pass


def real_money_endpoint() -> str:
    """Mainnet base URL, only when the operator explicitly unlocked it in the environment."""
    if os.environ.get(REAL_MONEY_ENV) != REAL_MONEY_PHRASE:
        raise RealMoneyLockedError(
            "real-money trading is locked; this project only trades on the Binance testnet "
            f"(set {REAL_MONEY_ENV}={REAL_MONEY_PHRASE} to override, at your own risk)"
        )
    return MAINNET_URL


@dataclass(frozen=True, slots=True)
class BinanceCredentials:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)

    @classmethod
    def from_env(cls, prefix: str = "BINANCE_TESTNET_") -> BinanceCredentials:
        key = os.environ.get(f"{prefix}API_KEY", "")
        secret = os.environ.get(f"{prefix}API_SECRET", "")
        if not key or not secret:
            raise ValueError(f"set {prefix}API_KEY and {prefix}API_SECRET in the environment")
        return cls(api_key=key, api_secret=secret)

    def __repr__(self) -> str:
        return f"BinanceCredentials(api_key='{self.api_key[:4]}…', api_secret='***')"


class RawHttpTransport(Protocol):
    def request(
        self, method: str, url: str, headers: dict[str, str]
    ) -> tuple[int, dict[str, object] | list[object]]: ...


class UrllibRawTransport:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds

    def request(
        self, method: str, url: str, headers: dict[str, str]
    ) -> tuple[int, dict[str, object] | list[object]]:
        req = urllib.request.Request(url=url, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                return response.status, _json(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, _json(exc.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ExchangeUnavailableError(f"{method} {url.split('?')[0]}: {exc}") from exc


def _json(raw: str) -> dict[str, object] | list[object]:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"msg": raw[:200]}
    return parsed if isinstance(parsed, (dict, list)) else {"value": parsed}


def _fmt(value: Decimal) -> str:
    return format(value.normalize(), "f")


class BinanceSpotClient:
    def __init__(
        self,
        credentials: BinanceCredentials,
        *,
        base_url: str = TESTNET_URL,
        transport: RawHttpTransport | None = None,
        clock_ms: Callable[[], int] | None = None,
        recv_window_ms: int = 5000,
    ) -> None:
        if base_url.rstrip("/") == MAINNET_URL:
            real_money_endpoint()  # raises RealMoneyLockedError unless explicitly unlocked
        self._credentials = credentials
        self._base_url = base_url.rstrip("/")
        self._transport = transport or UrllibRawTransport()
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._recv_window = recv_window_ms

    @property
    def base_url(self) -> str:
        return self._base_url

    def sign(self, params: dict[str, str]) -> str:
        """Query string with timestamp, recvWindow and the HMAC-SHA256 signature appended."""
        signed = {**params, "recvWindow": str(self._recv_window),
                  "timestamp": str(self._clock_ms())}
        query = urllib.parse.urlencode(signed)
        signature = hmac.new(
            self._credentials.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{query}&signature={signature}"

    def _call(self, method: str, path: str, params: dict[str, str]) -> object:
        url = f"{self._base_url}{path}?{self.sign(params)}"
        status, body = self._transport.request(
            method, url, {"X-MBX-APIKEY": self._credentials.api_key}
        )
        if status >= 500 or status in (408, 429, 418):
            raise ExchangeUnavailableError(f"{method} {path} answered {status}")
        if status >= 400:
            code = body.get("code") if isinstance(body, dict) else None
            msg = str(body.get("msg", "")) if isinstance(body, dict) else str(body)
            raise BinanceApiError(status, int(code) if isinstance(code, int) else None, msg)
        return body

    def new_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        client_order_id: str,
        price: Decimal | None = None,
        time_in_force: str = "GTC",
    ) -> dict[str, object]:
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": _fmt(quantity),
            "newClientOrderId": client_order_id,
            "newOrderRespType": "FULL",
        }
        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("limit orders need a price")
            params["price"] = _fmt(price)
            params["timeInForce"] = time_in_force
        return self._dict(self._call("POST", "/api/v3/order", params))

    def query_order(self, *, symbol: str, client_order_id: str) -> dict[str, object] | None:
        """The order by client id, or None if the exchange never received it (code -2013)."""
        try:
            return self._dict(
                self._call("GET", "/api/v3/order",
                           {"symbol": symbol.upper(), "origClientOrderId": client_order_id})
            )
        except BinanceApiError as exc:
            if exc.code == -2013:
                return None
            raise

    def cancel_order(self, *, symbol: str, client_order_id: str) -> dict[str, object]:
        return self._dict(
            self._call("DELETE", "/api/v3/order",
                       {"symbol": symbol.upper(), "origClientOrderId": client_order_id})
        )

    def cancel_open_orders(self, *, symbol: str) -> list[object]:
        try:
            body = self._call("DELETE", "/api/v3/openOrders", {"symbol": symbol.upper()})
        except BinanceApiError as exc:
            if exc.code == -2011:  # "Unknown order sent": nothing was open
                return []
            raise
        return body if isinstance(body, list) else []

    def open_orders(self, *, symbol: str) -> list[object]:
        body = self._call("GET", "/api/v3/openOrders", {"symbol": symbol.upper()})
        return body if isinstance(body, list) else []

    def account(self) -> dict[str, object]:
        return self._dict(self._call("GET", "/api/v3/account", {"omitZeroBalances": "true"}))

    @staticmethod
    def _dict(body: object) -> dict[str, object]:
        if not isinstance(body, dict):
            raise ValueError("expected a JSON object from Binance")
        return body
