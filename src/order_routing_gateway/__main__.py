from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal

from order_routing_gateway.binance_client import (
    BinanceApiError,
    BinanceCredentials,
    BinanceSpotClient,
    ExchangeUnavailableError,
)
from order_routing_gateway.ingest import parse_internal_order
from order_routing_gateway.models import (
    ExchangeId,
    GatewayConfig,
    RoutingMode,
    parse_exchange_id,
    parse_routing_mode,
)
from order_routing_gateway.pipeline import (
    run_routing_pipeline,
    serialize_routing_result,
    translate_order_pipeline,
)
from order_routing_gateway.testnet_router import TestnetOrderRouter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gateway de enrutamiento de órdenes hacia exchanges o paper trading.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    route = subparsers.add_parser("route", help="Enruta órdenes JSONL usando ticks de referencia.")
    route.add_argument("--orders", required=True)
    route.add_argument("--ticks", required=True)
    route.add_argument("--symbol", required=True)
    route.add_argument("--exchange", default="binance", choices=["binance", "coinbase"])
    route.add_argument(
        "--mode",
        default="paper",
        choices=["paper", "testnet", "live"],
        help="paper (simulado), testnet (Binance testnet) o live (dinero real, bloqueado).",
    )
    route.add_argument("--commission-rate", default="0.001")
    route.add_argument("--output", default=None)

    translate = subparsers.add_parser(
        "translate",
        help="Muestra la traducción de una orden interna al formato del exchange.",
    )
    translate.add_argument("--order-json", required=True)
    translate.add_argument("--symbol", required=True)
    translate.add_argument("--exchange", default="binance", choices=["binance", "coinbase"])

    testnet_help = "Binance testnet; claves en BINANCE_TESTNET_API_KEY / _API_SECRET."
    submit = subparsers.add_parser("submit", help=f"Envía una orden. {testnet_help}")
    submit.add_argument("--order-json", required=True)
    submit.add_argument("--symbol", required=True)
    submit.add_argument("--commission-rate", default="0.001")
    for name, help_text in (
        ("query", "Consulta una orden por client id"),
        ("cancel", "Cancela una orden por client id"),
        ("cancel-all", "Cancela todas las órdenes abiertas del símbolo"),
        ("open-orders", "Lista órdenes abiertas"),
        ("account", "Saldos de la cuenta testnet"),
    ):
        command = subparsers.add_parser(name, help=f"{help_text}. {testnet_help}")
        if name != "account":
            command.add_argument("--symbol", required=True)
        if name in ("query", "cancel"):
            command.add_argument("--client-order-id", required=True)

    return parser


EXIT_UNKNOWN_STATE = 75  # EX_TEMPFAIL: outcome unknown, reconcile with `query`


def _testnet_command(args: argparse.Namespace) -> int:
    """Testnet operations; prints one JSON document. Exit 75 when the outcome is unknown."""
    client = BinanceSpotClient(BinanceCredentials.from_env())
    try:
        if args.command == "submit":
            payload = json.loads(args.order_json)
            order = parse_internal_order(payload, default_symbol=args.symbol)
            config = GatewayConfig(
                exchange=ExchangeId.BINANCE,
                mode=RoutingMode.TESTNET,
                commission_rate=Decimal(args.commission_rate),
            )
            print(json.dumps(serialize_routing_result(
                TestnetOrderRouter(config, client).route_order(order)
            )))
        elif args.command == "query":
            print(json.dumps(client.query_order(symbol=args.symbol,
                                                client_order_id=args.client_order_id)))
        elif args.command == "cancel":
            print(json.dumps(client.cancel_order(symbol=args.symbol,
                                                 client_order_id=args.client_order_id)))
        elif args.command == "cancel-all":
            print(json.dumps(client.cancel_open_orders(symbol=args.symbol)))
        elif args.command == "open-orders":
            print(json.dumps(client.open_orders(symbol=args.symbol)))
        else:
            print(json.dumps(client.account()))
    except ExchangeUnavailableError as exc:
        print(json.dumps({"error": "exchange_unavailable", "detail": str(exc)}))
        return EXIT_UNKNOWN_STATE
    except BinanceApiError as exc:
        print(json.dumps({"error": "rejected", "code": exc.code, "detail": exc.message}))
        return 2
    return 0


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if args.command == "route":
        config = GatewayConfig(
            exchange=parse_exchange_id(args.exchange),
            mode=parse_routing_mode(args.mode),
            commission_rate=Decimal(args.commission_rate),
        )
        results = run_routing_pipeline(
            orders_path=args.orders,
            ticks_path=args.ticks,
            symbol=args.symbol,
            config=config,
        )
        rendered = json.dumps(results, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.write("\n")
            logging.getLogger(__name__).info(
                "wrote %s routing results to %s",
                len(results),
                args.output,
            )
            return
        print(rendered)
        return

    if args.command == "translate":
        payload = json.loads(args.order_json)
        if not isinstance(payload, dict):
            raise ValueError("order-json must be a JSON object")
        order = parse_internal_order(payload, default_symbol=args.symbol)
        config = GatewayConfig(
            exchange=parse_exchange_id(args.exchange),
            mode=parse_routing_mode("live"),
        )
        translated = translate_order_pipeline(order, config)
        print(json.dumps(translated, indent=2))
        return

    if args.command in {"submit", "query", "cancel", "cancel-all", "open-orders", "account"}:
        raise SystemExit(_testnet_command(args))

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
