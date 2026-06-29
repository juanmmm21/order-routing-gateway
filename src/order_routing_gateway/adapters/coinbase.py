from __future__ import annotations

from datetime import datetime
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


class CoinbaseOrderAdapter:
    """Traduce órdenes internas al formato POST /api/v3/brokerage/orders de Coinbase."""

    BASE_URL = "https://api.coinbase.com"

    def build_request(self, order: InternalOrder) -> ExchangeOrderRequest:
        product_id = _to_coinbase_product_id(order.symbol)
        side = "BUY" if order.side is OrderSide.BUY else "SELL"

        if order.order_type is OrderType.MARKET:
            order_configuration = {
                "market_market_ioc": {
                    "quote_size" if order.side is OrderSide.BUY else "base_size": _format_decimal(
                        order.quantity
                    ),
                }
            }
        else:
            if order.limit_price is None:
                raise ValueError("limit_price is required for limit orders")
            order_configuration = {
                "limit_limit_gtc": {
                    "base_size": _format_decimal(order.quantity),
                    "limit_price": _format_decimal(order.limit_price),
                    "post_only": "false",
                }
            }

        payload = {
            "client_order_id": order.client_order_id,
            "product_id": product_id,
            "side": side,
            "order_configuration": _serialize_configuration(order_configuration),
        }

        return ExchangeOrderRequest(
            exchange=ExchangeId.COINBASE,
            endpoint=f"{self.BASE_URL}/api/v3/brokerage/orders",
            method="POST",
            payload=payload,
            client_order_id=order.client_order_id,
        )

    def parse_acknowledgement(
        self,
        order: InternalOrder,
        response_body: dict[str, object],
    ) -> OrderAcknowledgement:
        if response_body.get("error") is not None:
            error = response_body.get("error")
            message = str(error) if error is not None else "order rejected"
            return OrderAcknowledgement(
                client_order_id=order.client_order_id,
                exchange_order_id=f"rejected-{order.client_order_id}",
                exchange=ExchangeId.COINBASE,
                status=OrderStatus.REJECTED,
                submitted_at=order.submitted_at,
                message=message,
            )

        order_id = _extract_order_id(response_body)
        return OrderAcknowledgement(
            client_order_id=order.client_order_id,
            exchange_order_id=order_id,
            exchange=ExchangeId.COINBASE,
            status=OrderStatus.ACCEPTED,
            submitted_at=order.submitted_at,
            message="order accepted",
        )

    def parse_fill(
        self,
        order: InternalOrder,
        response_body: dict[str, object],
        commission_rate: object,
    ) -> RoutedFill:
        if not isinstance(commission_rate, Decimal):
            raise TypeError("commission_rate must be Decimal")

        order_id = _extract_order_id(response_body)
        fill_price = _extract_fill_price(response_body, order)
        filled_size = _extract_filled_size(response_body, order)
        filled_at = _extract_filled_at(response_body, order)
        commission = fill_price * filled_size * commission_rate

        return RoutedFill(
            client_order_id=order.client_order_id,
            exchange_order_id=order_id,
            exchange=ExchangeId.COINBASE,
            symbol=order.symbol,
            side=order.side,
            quantity=filled_size,
            fill_price=fill_price,
            commission=commission,
            filled_at=filled_at,
        )


def _to_coinbase_product_id(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "")
    if normalized.endswith("USDT"):
        base = normalized[:-4]
        return f"{base}-USD"
    if "-" in symbol:
        return symbol.upper()
    if normalized.endswith("USD") and len(normalized) > 3:
        base = normalized[:-3]
        return f"{base}-USD"
    raise ValueError(f"unsupported symbol for coinbase: {symbol}")


def _serialize_configuration(configuration: dict[str, dict[str, str]]) -> str:
    import json

    return json.dumps(configuration, separators=(",", ":"))


def _extract_order_id(response_body: dict[str, object]) -> str:
    success = response_body.get("success_response")
    if isinstance(success, dict):
        order_id = success.get("order_id")
        if isinstance(order_id, str) and order_id:
            return order_id
    order_id = response_body.get("order_id")
    if isinstance(order_id, str) and order_id:
        return order_id
    raise ValueError("missing order_id in coinbase response")


def _extract_fill_price(response_body: dict[str, object], order: InternalOrder) -> Decimal:
    order_payload = response_body.get("order")
    if isinstance(order_payload, dict):
        average_filled_price = order_payload.get("average_filled_price")
        if isinstance(average_filled_price, str):
            return Decimal(average_filled_price)
    if order.limit_price is not None:
        return order.limit_price
    raise ValueError("missing average_filled_price in coinbase response")


def _extract_filled_size(response_body: dict[str, object], order: InternalOrder) -> Decimal:
    order_payload = response_body.get("order")
    if isinstance(order_payload, dict):
        filled_size = order_payload.get("filled_size")
        if isinstance(filled_size, str):
            return Decimal(filled_size)
    return order.quantity


def _extract_filled_at(response_body: dict[str, object], order: InternalOrder) -> datetime:
    order_payload = response_body.get("order")
    if isinstance(order_payload, dict):
        created_time = order_payload.get("created_time")
        if isinstance(created_time, str):
            return utc_from_iso8601(created_time)
    return order.submitted_at


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")
