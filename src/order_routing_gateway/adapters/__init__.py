from __future__ import annotations

from order_routing_gateway.adapters.binance import BinanceOrderAdapter
from order_routing_gateway.adapters.coinbase import CoinbaseOrderAdapter
from order_routing_gateway.models import ExchangeId
from order_routing_gateway.protocols import ExchangeOrderAdapter


def create_exchange_adapter(exchange: ExchangeId) -> ExchangeOrderAdapter:
    if exchange is ExchangeId.BINANCE:
        return BinanceOrderAdapter()
    if exchange is ExchangeId.COINBASE:
        return CoinbaseOrderAdapter()
    raise ValueError(f"unsupported exchange: {exchange}")
