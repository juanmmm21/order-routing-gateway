from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from order_routing_gateway.adapters.binance import BinanceOrderAdapter
from order_routing_gateway.adapters.coinbase import CoinbaseOrderAdapter
from order_routing_gateway.models import InternalOrder, OrderSide, OrderType


def _sample_order() -> InternalOrder:
    return InternalOrder(
        client_order_id="ord-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        submitted_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )


def test_binance_adapter_builds_market_order_payload() -> None:
    request = BinanceOrderAdapter().build_request(_sample_order())
    assert request.method == "POST"
    assert request.payload["symbol"] == "BTCUSDT"
    assert request.payload["side"] == "BUY"
    assert request.payload["type"] == "MARKET"
    assert request.payload["quantity"] == "0.01"


def test_coinbase_adapter_maps_symbol_to_product_id() -> None:
    request = CoinbaseOrderAdapter().build_request(_sample_order())
    assert request.payload["product_id"] == "BTC-USD"
    assert request.payload["side"] == "BUY"
    assert "order_configuration" in request.payload


def test_binance_adapter_parses_fill_response() -> None:
    order = _sample_order()
    adapter = BinanceOrderAdapter()
    response = {
        "orderId": "12345",
        "status": "FILLED",
        "executedQty": "0.01",
        "cummulativeQuoteQty": "1000",
        "transactTime": 1_704_110_400_000,
    }
    fill = adapter.parse_fill(order, response, Decimal("0.001"))
    assert fill.fill_price == Decimal("100000")
    assert fill.quantity == Decimal("0.01")
