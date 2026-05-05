"""Main entry point for langgraph-demo."""

import argparse
import logging

from langgraph_demo.app import (
    configure,
    ui,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph Demo")
    parser.add_argument("--log", action="store_true", default=False, help="Enable debug logging")
    parser.add_argument("--log-file", default=None, metavar="FILE", help="Log file path (default: stderr)")
    parser.add_argument(
        "--no-url-guard", action="store_false", dest="url_guard", help="Disable URL guard (allow all navigation)"
    )
    args = parser.parse_args()

    if args.log or args.log_file:
        handler: logging.Handler = logging.FileHandler(args.log_file) if args.log_file else logging.StreamHandler()
        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[handler],
        )
        logging.getLogger("langgraph_demo").setLevel(logging.DEBUG)

    configure(url_guard_enabled=args.url_guard)
    ui.launch(inbrowser=True)


if __name__ == "__main__":
    main()
