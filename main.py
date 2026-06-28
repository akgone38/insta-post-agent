"""
Instagram Posting Agent — FastAPI Server

Receives photos from Telegram, generates AI captions, and posts to Instagram.
Built for State Park RV Village (Lockhart, TX).
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update

from app.config import settings
from app.telegram.bot import create_telegram_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Create temp_images directory for serving photos
TEMP_IMAGE_DIR = Path("temp_images")
TEMP_IMAGE_DIR.mkdir(exist_ok=True)

# Create Telegram application (module-level so it's shared)
telegram_app = create_telegram_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown tasks."""

    # --- Startup ---
    logger.info("=" * 60)
    logger.info("🏕️  State Park RV Village — Instagram Posting Agent")
    logger.info("=" * 60)

    # Initialize Telegram bot
    await telegram_app.initialize()
    await telegram_app.start()

    # Register webhook with Telegram (with retry for 429 rate limits)
    webhook_url = settings.telegram_webhook_url
    logger.info("Setting Telegram webhook to: %s", webhook_url)

    async with httpx.AsyncClient() as client:
        for attempt in range(5):
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
                json={"url": webhook_url, "drop_pending_updates": True},
            )
            result = resp.json()
            if result.get("ok"):
                logger.info("✅ Telegram webhook set successfully")
                break
            elif resp.status_code == 429:
                retry_after = result.get("parameters", {}).get("retry_after", 5)
                logger.warning("⏳ Rate limited (429). Waiting %ds...", retry_after)
                await asyncio.sleep(retry_after)
            else:
                logger.error("❌ Failed to set webhook: %s", result)
                break

    logger.info("🚀 Server is ready! Waiting for photos on Telegram...")
    logger.info("=" * 60)

    yield

    # --- Shutdown ---
    logger.info("Shutting down...")
    await telegram_app.stop()
    await telegram_app.shutdown()

    # Clean up temp images
    for f in TEMP_IMAGE_DIR.iterdir():
        try:
            f.unlink()
        except Exception:
            pass

    logger.info("Goodbye! 👋")


# Create FastAPI app
app = FastAPI(
    title="Instagram Posting Agent",
    description="AI-powered Instagram posting agent for State Park RV Village",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve temp images as static files (Instagram needs to fetch them via public URL)
app.mount("/images", StaticFiles(directory="temp_images"), name="images")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "instagram-posting-agent",
        "instagram_account_id": settings.instagram_account_id,
    }


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive incoming updates from Telegram.

    This endpoint is called by Telegram whenever the bot receives a message.
    We process it in the background to return 200 OK immediately and avoid duplicate retries.
    """
    try:
        data = await request.json()
        logger.info("Received Telegram update")
        logger.debug("Update data: %s", data)

        # Parse and process the update in the background
        update = Update.de_json(data=data, bot=telegram_app.bot)
        background_tasks.add_task(telegram_app.process_update, update)

        return JSONResponse(content={"ok": True})

    except Exception as e:
        logger.error("Error processing Telegram update: %s", e, exc_info=True)
        return JSONResponse(
            content={"ok": False, "error": str(e)},
            status_code=500,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
