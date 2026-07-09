"""Bot notification helper used by the worker."""

from __future__ import annotations

from aiogram import Bot

from apps.api.app.core.config import get_settings


async def send_message(telegram_id: int, text: str) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        return
    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.send_message(chat_id=telegram_id, text=text, disable_web_page_preview=True)
    finally:
        await bot.session.close()
