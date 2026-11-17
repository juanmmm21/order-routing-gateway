from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from order_routing_gateway.binance_client import (
    MAINNET_URL,
    TESTNET_URL,
    BinanceApiError,
    BinanceCredentials,
    BinanceSpotClient,
    ExchangeUnavailableError,
    RealMoneyLockedError,
)
from order_routing_gateway.gateway import OrderRoutingGateway
from order_routing_gateway.http_transport import MockHttpTransport
from order_routing_gateway.live_router import LiveOrderRouter
from order_routing_gateway.models import (
    ExchangeId,
    GatewayConfig,
    InternalOrder,
    OrderSide,
    OrderStatus,
    OrderType,
    RoutingMode,
)

# Example from Binance's "SIGNED endpoint" documentation.
DOC_SECRET = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
DOC_SIGNATURE = "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"
CREDS = BinanceCredentials(api_key="test-key-not-real", api_secret=DOC_SECRET)


class FakeTransport:
    def __init__(self, responses: list[tuple[int, object] | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def request(self, method: str, url: str, headers: dict[str, str]) -> tuple[int, object]:
        self.calls.append((method, url, headers))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[return-value]


def _client(transport: FakeTransport) -> BinanceSpotClient:
    return BinanceSpotClient(CREDS, transport=transport, clock_ms=lambda: 1499827319559)


def test_signature_matches_binance_documentation() -> None:
    params = {
        "symbol": "LTCBTC",
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "1",
        "price": "0.1",
    }
    query = _client(FakeTransport([])).sign(params)
    assert query.endswith(f"&signature={DOC_SIGNATURE}")
    assert "recvWindow=5000&timestamp=1499827319559" in query


def test_orders_go_to_the_testnet_signed_with_the_key_header() -> None:
    transport = FakeTransport(
        [
            (
                200,
                {
                    "orderId": 7,
                    "status": "FILLED",
                    "executedQty": "0.001",
                    "cummulativeQuoteQty": "65.0",
                    "fills": [{"price": "65000", "qty": "0.001", "tradeId": 1}],
                },
            )
        ]
    )
    body = _client(transport).new_order(
        symbol="btcusdt",
        side="buy",
        order_type="market",
        quantity=Decimal("0.001"),
        client_order_id="qt-1",
    )
    method, url, headers = transport.calls[0]
    assert method == "POST"
    assert url.startswith(f"{TESTNET_URL}/api/v3/order?symbol=BTCUSDT&side=BUY&type=MARKET")
    assert "newClientOrderId=qt-1" in url and "signature=" in url
    assert headers == {"X-MBX-APIKEY": "test-key-not-real"}
    assert body["status"] == "FILLED"


def test_rejections_and_unknown_outcomes_are_different_errors() -> None:
    client = _client(
        FakeTransport(
            [
                (400, {"code": -2010, "msg": "Account has insufficient balance"}),
                (503, {}),
                TimeoutError("read timed out"),
            ]
        )
    )
    order = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": Decimal("1"),
        "client_order_id": "x",
    }
    with pytest.raises(BinanceApiError) as rejected:
        client.new_order(**order)  # type: ignore[arg-type]
    assert rejected.value.code == -2010
    with pytest.raises(ExchangeUnavailableError):
        client.new_order(**order)  # type: ignore[arg-type]
    with pytest.raises(TimeoutError):
        client.new_order(**order)  # type: ignore[arg-type]


def test_query_unknown_order_returns_none_and_cancel_all_tolerates_empty() -> None:
    client = _client(
        FakeTransport(
            [
                (400, {"code": -2013, "msg": "Order does not exist."}),
                (400, {"code": -2011, "msg": "Unknown order sent."}),
            ]
        )
    )
    assert client.query_order(symbol="BTCUSDT", client_order_id="ghost") is None
    assert client.cancel_open_orders(symbol="BTCUSDT") == []


def test_credentials_only_from_environment_and_never_printed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)
    with pytest.raises(ValueError):
        BinanceCredentials.from_env()
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "abcd1234")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "super-secret-value")
    creds = BinanceCredentials.from_env()
    assert "super-secret-value" not in repr(creds) and "abcd1234" not in repr(creds)


ORDER = InternalOrder(
    client_order_id="ord-1",
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=Decimal("0.01"),
    submitted_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def test_real_money_is_locked_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORDER_ROUTING_ALLOW_REAL_MONEY", raising=False)
    transport = MockHttpTransport()
    router = LiveOrderRouter(
        GatewayConfig(ExchangeId.BINANCE, RoutingMode.LIVE), transport=transport
    )
    with pytest.raises(RealMoneyLockedError):
        router.route_order(ORDER)
    assert transport.sent_requests == []  # nothing left the process
    with pytest.raises(RealMoneyLockedError):
        BinanceSpotClient(CREDS, base_url=MAINNET_URL)
    monkeypatch.setenv("ORDER_ROUTING_ALLOW_REAL_MONEY", "yes")  # a vague "yes" is not enough
    with pytest.raises(RealMoneyLockedError):
        router.route_order(ORDER)


def test_gateway_testnet_mode_routes_and_parses_fills(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "s")
    transport = FakeTransport(
        [
            (
                200,
                {
                    "orderId": 9,
                    "status": "FILLED",
                    "executedQty": "0.01",
                    "cummulativeQuoteQty": "650",
                    "fills": [{"price": "65000", "qty": "0.01", "tradeId": 3}],
                },
            ),
            (400, {"code": -1013, "msg": "Filter failure: LOT_SIZE"}),
        ]
    )
    gateway = OrderRoutingGateway(
        GatewayConfig(ExchangeId.BINANCE, RoutingMode.TESTNET), raw_transport=transport
    )
    result = gateway.router.route_order(ORDER)
    assert result.fill is not None and result.fill.fill_price == Decimal("65000")
    rejected = gateway.router.route_order(ORDER)
    assert rejected.acknowledgement.status is OrderStatus.REJECTED
    assert "LOT_SIZE" in (rejected.acknowledgement.message or "")
