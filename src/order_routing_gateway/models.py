from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class ExchangeId(StrEnum):
    BINANCE = "binance"
    COINBASE = "coinbase"


class RoutingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    ACCEPTED = "accepted"
    FILLED = "filled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class InternalOrder:
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    submitted_at: datetime
    signal_id: str = ""
    limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.client_order_id:
            raise ValueError("client_order_id must not be empty")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        if self.submitted_at.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        if self.limit_price is not None and self.limit_price <= Decimal("0"):
            raise ValueError("limit_price must be positive")


@dataclass(frozen=True, slots=True)
class PriceTick:
    symbol: str
    price: Decimal
    event_time: datetime

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.price <= Decimal("0"):
            raise ValueError("price must be positive")
        if self.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ExchangeOrderRequest:
    exchange: ExchangeId
    endpoint: str
    method: str
    payload: dict[str, str]
    client_order_id: str

    def __post_init__(self) -> None:
        if not self.endpoint:
            raise ValueError("endpoint must not be empty")
        if not self.method:
            raise ValueError("method must not be empty")
        if not self.client_order_id:
            raise ValueError("client_order_id must not be empty")


@dataclass(frozen=True, slots=True)
class OrderAcknowledgement:
    client_order_id: str
    exchange_order_id: str
    exchange: ExchangeId
    status: OrderStatus
    submitted_at: datetime
    message: str = ""

    def __post_init__(self) -> None:
        if not self.client_order_id:
            raise ValueError("client_order_id must not be empty")
        if not self.exchange_order_id:
            raise ValueError("exchange_order_id must not be empty")
        if self.submitted_at.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RoutedFill:
    client_order_id: str
    exchange_order_id: str
    exchange: ExchangeId
    symbol: str
    side: OrderSide
    quantity: Decimal
    fill_price: Decimal
    commission: Decimal
    filled_at: datetime

    def __post_init__(self) -> None:
        if not self.client_order_id:
            raise ValueError("client_order_id must not be empty")
        if not self.exchange_order_id:
            raise ValueError("exchange_order_id must not be empty")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        if self.fill_price <= Decimal("0"):
            raise ValueError("fill_price must be positive")
        if self.commission < Decimal("0"):
            raise ValueError("commission must be non-negative")
        if self.filled_at.tzinfo is None:
            raise ValueError("filled_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    exchange: ExchangeId
    mode: RoutingMode
    commission_rate: Decimal = Decimal("0.001")

    def __post_init__(self) -> None:
        if self.commission_rate < Decimal("0"):
            raise ValueError("commission_rate must be non-negative")


@dataclass(frozen=True, slots=True)
class RoutingResult:
    acknowledgement: OrderAcknowledgement
    fill: RoutedFill | None


def utc_from_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def decimal_from_value(value: object, field_name: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        return Decimal(str(value))
    raise ValueError(f"{field_name} must be numeric")


def parse_order_side(value: str) -> OrderSide:
    try:
        return OrderSide(value)
    except ValueError as exc:
        raise ValueError(f"unsupported order side: {value}") from exc


def parse_order_type(value: str) -> OrderType:
    try:
        return OrderType(value)
    except ValueError as exc:
        raise ValueError(f"unsupported order type: {value}") from exc


def parse_exchange_id(value: str) -> ExchangeId:
    try:
        return ExchangeId(value)
    except ValueError as exc:
        raise ValueError(f"unsupported exchange: {value}") from exc


def parse_routing_mode(value: str) -> RoutingMode:
    try:
        return RoutingMode(value)
    except ValueError as exc:
        raise ValueError(f"unsupported routing mode: {value}") from exc
