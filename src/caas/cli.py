"""CLI entrypoints for local reference runs."""
from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="caas-api")
    parser.add_argument(
        "--app",
        choices=("multiscope", "legacy"),
        default="multiscope",
        help="Which FastAPI app to serve",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    import uvicorn

    target = (
        "caas.multiscope_api:app" if args.app == "multiscope" else "caas.api:app"
    )
    if not os.getenv("CAAS_UNSAFE_DEV_HEADERS") and args.app == "multiscope":
        print(
            "Note: set CAAS_UNSAFE_DEV_HEADERS=1 for local header identity only; "
            "never enable on a public network."
        )
    uvicorn.run(target, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
