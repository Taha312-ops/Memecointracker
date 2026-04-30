"""
main.py — MemeCoin Tracker Bot entry point
Run: python3 main.py
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
load_dotenv()

from telegram.ext import Application

from services.database import init_db
from services.monitor import monitor_loop
from handlers.handlers import build_conversation_handler, register_callbacks

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    await init_db()
    logger.info("✅ Database initialized")
    asyncio.create_task(monitor_loop(app))
    logger.info("✅ Wallet monitor started")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(build_conversation_handler())
    register_callbacks(app)

    logger.info("🚀 Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
