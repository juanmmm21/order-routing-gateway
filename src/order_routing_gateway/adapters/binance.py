from __future__ import annotations

from decimal import Decimal

from order_routing_gateway.models import (
    ExchangeId,
    ExchangeOrderRequest,
    InternalOrder,
    OrderAcknowledgement,
    OrderSide,
    OrderStatus,
    OrderType,
    RoutedFill,
    utc_from_iso8601,
)


class BinanceOrderAdapter:
    """Traduce órdenes internas al formato POST /api/v3/order de Binance Spot."""

    BASE_URL = "https://api.binance.com"

    def build_request(self, order: InternalOrder) -> ExchangeOrderRequest:
        side = "BUY" if order.side is OrderSide.BUY else "SELL"
        order_type = "MARKET" if order.order_type is OrderType.MARKET else "LIMIT"

        payload: dict[str, str] = {
            "symbol": order.symbol.upper(),
            "side": side,
            "type": order_type,
            "quantity": _format_decimal(order.quantity),
            "newClientOrderId": order.client_order_id,
        }
        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            payload["price"] = _format_decimal(order.limit_price)
            payload["timeInForce"] = "GTC"

        return ExchangeOrderRequest(
            exchange=ExchangeId.BINANCE,
            endpoint=f"{self.BASE_URL}/api/v3/order",
            method="POST",
            payload=payload,
            client_order_id=order.client_order_id,
        )

    def parse_acknowledgement(
        self,
        order: InternalOrder,
        response_body: dict[str, object],
    ) -> OrderAcknowledgement:
        if response_body.get("error") is not None or response_body.get("code") is not None:
            code = response_body.get("code")
            message = str(response_body.get("msg", response_body.get("error", "order rejected")))
            if code is not None:
                message = f"{code}: {message}"
            return OrderAcknowledgement(
                client_order_id=order.client_order_id,
                exchange_order_id=f"rejected-{order.client_order_id}",
                exchange=ExchangeId.BINANCE,
                status=OrderStatus.REJECTED,
                submitted_at=order.submitted_at,
                message=message,
            )

        exchange_order_id = _require_str(response_body, "orderId")
        status_raw = _require_str(response_body, "status")
        status = _map_binance_status(status_raw)

        return OrderAcknowledgement(
            client_order_id=order.client_order_id,
            exchange_order_id=exchange_order_id,
            exchange=ExchangeId.BINANCE,
            status=status,
            submitted_at=order.submitted_at,
            message=status_raw,
        )

    def parse_fill(
        self,
        order: InternalOrder,
        response_body: dict[str, object],
        commission_rate: object,
    ) -> RoutedFill:
        if not isinstance(commission_rate, Decimal):
            raise TypeError("commission_rate must be Decimal")

        fills = response_body.get("fills")
        if isinstance(fills, list) and fills:
            return _parse_fills_array(order, fills, commission_rate)

        executed_qty = Decimal(_require_str(response_body, "executedQty"))
        if executed_qty <= Decimal("0"):
            raise ValueError("executedQty must be positive for a fill")

        if order.order_type is OrderType.MARKET:
            cummulative_quote = Decimal(_require_str(response_body, "cummulativeQuoteQty"))
            fill_price = cummulative_quote / executed_qty
        else:
            fill_price = Decimal(_require_str(response_body, "price"))

        transact_time = response_body.get("transactTime")
        if isinstance(transact_time, int):
            filled_at = utc_from_iso8601(
                _millis_to_iso(transact_time),
            )
        else:
            filled_at = order.submitted_at

        commission = fill_price * executed_qty * commission_rate
        return RoutedFill(
            client_order_id=order.client_order_id,
            exchange_order_id=_require_str(response_body, "orderId"),
            exchange=ExchangeId.BINANCE,
            symbol=order.symbol,
            side=order.side,
            quantity=executed_qty,
            fill_price=fill_price,
            commission=commission,
            filled_at=filled_at,
        )


def _parse_fills_array(
    order: InternalOrder,
    fills: list[object],
    commission_rate: Decimal,
) -> RoutedFill:
    total_qty = Decimal("0")
    total_notional = Decimal("0")
    exchange_order_id = ""

    for entry in fills:
        if not isinstance(entry, dict):
            raise ValueError("each fill entry must be an object")
        price = Decimal(_require_str(entry, "price"))
        qty = Decimal(_require_str(entry, "qty"))
        total_qty += qty
        total_notional += price * qty
        if not exchange_order_id:
            exchange_order_id = str(entry.get("tradeId", order.client_order_id))

    if total_qty <= Decimal("0"):
        raise ValueError("aggregate fill quantity must be positive")

    fill_price = total_notional / total_qty
    commission = total_notional * commission_rate
    return RoutedFill(
        client_order_id=order.client_order_id,
        exchange_order_id=exchange_order_id,
        exchange=ExchangeId.BINANCE,
        symbol=order.symbol,
        side=order.side,
        quantity=total_qty,
        fill_price=fill_price,
        commission=commission,
        filled_at=order.submitted_at,
    )


def _map_binance_status(status: str) -> OrderStatus:
    if status in {"NEW", "PARTIALLY_FILLED"}:
        return OrderStatus.ACCEPTED
    if status == "FILLED":
        return OrderStatus.FILLED
    return OrderStatus.REJECTED


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _require_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        raise ValueError(f"expected string field '{key}'")
    return value


def _millis_to_iso(value: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
