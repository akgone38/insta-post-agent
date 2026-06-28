"""Telegram bot setup and application builder."""

import logging

from telegram.ext import Application, MessageHandler, CommandHandler, filters

from app.config import settings

logger = logging.getLogger(__name__)


def create_telegram_app() -> Application:
    """
    Create and configure the Telegram bot application.

    Returns a built Application instance ready for webhook processing.
    Handlers are registered here but the actual processing functions
    are imported from handlers.py to keep concerns separated.
    """
    from app.telegram.handlers import handle_media, handle_start, handle_help

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_help))

    # Media handler (Photos and Videos/Reels)
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))

    # Catch-all for non-media messages
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        _handle_text_only,
    ))

    logger.info("Telegram bot application configured with handlers")
    return app


async def _handle_text_only(update, context):
    """Reply when user sends text without a photo or video."""
    await update.message.reply_text(
        "📸 Please send me a **photo** or **video** to post on Instagram & Facebook!\n\n"
        "You can also add a caption with the media to give me context "
        "about what the post should say.",
        parse_mode="Markdown",
    )
