from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "shared"))

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from apps.api.app.core.config import get_settings
from apps.api.app.core.logging import configure_logging, get_logger

log = get_logger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    settings = get_settings()
    webapp_url = settings.telegram_webapp_url
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Open Crypto Intelligence",
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        ]
    )
    await message.answer(
        "Welcome to Crypto Intelligence Platform.\n\n"
        "This is a read-only wallet intelligence service.\n"
        "We never ask for private keys or seed phrases.\n\n"
        "Tap the button below to open the Mini App.",
        reply_markup=keyboard,
    )


@router.message(F.web_app_data)
async def on_web_app_data(message: Message) -> None:
    await message.answer("Received. Use the Mini App for actions.")


async def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.error("TELEGRAM_BOT_TOKEN not configured; bot cannot start")
        sys.exit(1)
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    log.info("bot starting polling")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
