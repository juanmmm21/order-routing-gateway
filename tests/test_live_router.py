from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from order_routing_gateway.http_transport import MockHttpTransport
from order_routing_gateway.live_router import LiveOrderRouter
from order_routing_gateway.models import (
    ExchangeId,
    GatewayConfig,
    InternalOrder,
    OrderSide,
    OrderType,
    RoutingMode,
)


def test_live_router_uses_mock_transport() -> None:
    order = InternalOrder(
        client_order_id="ord-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        submitted_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )
    transport = MockHttpTransport(
        responses={
            "ord-1": {
                "orderId": "999",
                "status": "FILLED",
                "executedQty": "0.01",
                "cummulativeQuoteQty": "1000",
                "transactTime": 1_704_110_400_000,
            }
        }
    )
    router = LiveOrderRouter(
        config=GatewayConfig(exchange=ExchangeId.BINANCE, mode=RoutingMode.LIVE),
        transport=transport,
    )
    result = router.route_order(order)
    assert result.fill is not None
    assert len(transport.sent_requests) == 1
    assert transport.sent_requests[0]["payload"]["newClientOrderId"] == "ord-1"
