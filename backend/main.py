"""Compatibility entrypoint for the Scraper Flow Studio FastAPI application."""

from app import app, main


if __name__ == "__main__":
    import argparse

    from core.settings import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=settings.backend_port)
    args = parser.parse_args()
    main(port=args.port)
