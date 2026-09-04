from __future__ import annotations

import argparse
import logging
import os
import signal
import time
import uuid

from app.server.config import load_server_config
from app.server.repositories import GitHubAppClient, PostgresStore
from app.server.services import process_one_job
from src.engine.gateway import SubprocessReviewEngine

logger = logging.getLogger(__name__)


def _shutdown(_signum, _frame) -> None:
    """Turn Docker SIGTERM and terminal Ctrl+C into one cleanup path."""
    raise KeyboardInterrupt


def main() -> int:
    parser = argparse.ArgumentParser(description="DUT AI PostgreSQL review worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)
    try:
        config = load_server_config()
        logger.info(
            "worker starting once=%s repositories=%s llm_base_url=%s model=%s",
            args.once, sorted(config.allowed_repositories),
            config.llm_base_url, config.llm_model,
        )
        store = PostgresStore(config.database_url)
        github = GitHubAppClient(config)
        engine = SubprocessReviewEngine(
            base_url=config.llm_base_url, model=config.llm_model,
            api_key=config.llm_api_key,
        )
        store.migrate()
        store.sync_installation(github.installation(), github.repositories())
        logger.info("worker synced GitHub installation repositories")
        lease_id = uuid.uuid4().hex
        while True:
            worked = process_one_job(
                config, store, github, engine, lease_id=lease_id
            )
            if args.once:
                return 0
            if not worked:
                logger.debug("worker idle; no queued jobs")
                time.sleep(2)
    except KeyboardInterrupt:
        logger.info("shutdown requested; worker stopped cleanly")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
