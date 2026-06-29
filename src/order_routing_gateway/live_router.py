from __future__ import annotations

import logging

from order_routing_gateway.adapters import create_exchange_adapter
from order_routing_gateway.http_transport import UrllibHttpTransport
from order_routing_gateway.models import (
    GatewayConfig,
    InternalOrder,
    OrderStatus,
    PriceTick,
    RoutingResult,
)
from order_routing_gateway.protocols import ExchangeOrderAdapter, HttpTransport

logger = logging.getLogger(__name__)


class LiveOrderRouter:
    """Envía órdenes al exchange vía REST usando el adaptador configurado."""

    def __init__(
        self,
        config: GatewayConfig,
        adapter: ExchangeOrderAdapter | None = None,
        transport: HttpTransport | None = None,
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        self._config = config
        self._adapter = adapter or create_exchange_adapter(config.exchange)
        self._transport = transport or UrllibHttpTransport()
        self._api_key = api_key
        self._api_secret = api_secret

    def route_order(
        self,
        order: InternalOrder,
        market_price: PriceTick | None = None,
    ) -> RoutingResult:
        _ = market_price
        request = self._adapter.build_request(order)
        headers = self._build_auth_headers(request.payload)

        try:
            response = self._transport.send(
                method=request.method,
                url=request.endpoint,
                payload=request.payload,
                headers=headers,
            )
        except ConnectionError:
            raise
        except Exception as exc:
            logger.exception("unexpected error routing order %s", order.client_order_id)
            raise RuntimeError(f"failed to route order {order.client_order_id}") from exc

        acknowledgement = self._adapter.parse_acknowledgement(order, response)
        if acknowledgement.status is OrderStatus.REJECTED:
            return RoutingResult(acknowledgement=acknowledgement, fill=None)
        fill = None
        if acknowledgement.status is OrderStatus.FILLED:
            fill = self._adapter.parse_fill(order, response, self._config.commission_rate)

        logger.info(
            "live route client_order_id=%s exchange=%s status=%s",
            order.client_order_id,
            self._config.exchange.value,
            acknowledgement.status.value,
        )
        return RoutingResult(acknowledgement=acknowledgement, fill=fill)

    def translate_order(self, order: InternalOrder) -> dict[str, str]:
        """Expone la traducción sin enviar la orden (útil para dry-run)."""
        request = self._adapter.build_request(order)
        return dict(request.payload)

    def _build_auth_headers(self, payload: dict[str, str]) -> dict[str, str]:
        _ = payload
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-MBX-APIKEY"] = self._api_key
        if self._api_secret:
            headers["CB-ACCESS-KEY"] = self._api_key
        return headers
