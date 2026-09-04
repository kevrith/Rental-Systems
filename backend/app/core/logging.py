import logging


def configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    # We don't use create_async_engine(echo=True) because it attaches SQLAlchemy's
    # own handler directly to this logger (bypassing our config) and causes double
    # logging once records also propagate to root. Controlling the level directly
    # gives us SQL echo in debug mode through the single handler above.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO if debug else logging.WARNING)
