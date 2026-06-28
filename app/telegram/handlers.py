"""Telegram message handlers — orchestrates the full pipeline."""

import logging
import uuid
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings
from app.ai.caption_gen import generate_caption
from app.instagram.publisher import publish_photo, InstagramPublishError
from app.facebook.publisher import publish_to_facebook, FacebookPublishError

logger = logging.getLogger(__name__)

# Directory for temporarily storing images
TEMP_IMAGE_DIR = Path("temp_images")
TEMP_IMAGE_DIR.mkdir(exist_ok=True)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text(
        "🏕️ *Welcome to the State Park RV Village Instagram Bot!*\n\n"
        "Send me a photo and I'll:\n"
        "1️⃣ Analyze the image with AI\n"
        "2️⃣ Generate an engaging caption\n"
        "3️⃣ Post it to Instagram automatically\n\n"
        "💡 *Tip:* Add a caption with your photo to give me context "
        "(e.g., \"new site setup\" or \"sunset at the park\").\n\n"
        "Type /help for more info.",
        parse_mode="Markdown",
    )


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    await update.message.reply_text(
        "📖 *How to use this bot:*\n\n"
        "📸 *Post a photo:* Send any photo (with optional caption)\n"
        "   → I'll generate an engaging caption and post to Instagram\n\n"
        "💬 *Custom context:* Add a message with your photo like:\n"
        "   • \"Beautiful sunset tonight\"\n"
        "   • \"New amenity installed\"\n"
        "   • \"Guest appreciation event\"\n\n"
        "🤖 The AI will use your context + image analysis to write "
        "the perfect Instagram caption with relevant hashtags.\n\n"
        "⏱️ *Processing time:* Usually 15-30 seconds.",
        parse_mode="Markdown",
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming photos — the main pipeline.

    Flow:
    1. Download the highest resolution photo from Telegram
    2. Generate a caption using Gemini AI
    3. Upload to Instagram via Graph API
    4. Reply with status
    """
    message = update.message
    user = message.from_user
    logger.info("Received photo from user %s (%s)", user.username, user.id)

    # Send "processing" status
    status_msg = await message.reply_text(
        "⏳ *Processing your photo...*\n\n"
        "🔍 Step 1/3: Downloading image...",
        parse_mode="Markdown",
    )

    try:
        # Step 1: Download the photo (highest resolution)
        photo = message.photo[-1]  # Last element = highest resolution
        user_caption = message.caption  # Optional caption from user

        # Generate a unique filename
        file_id = str(uuid.uuid4())[:8]
        image_filename = f"{file_id}.jpg"
        image_path = TEMP_IMAGE_DIR / image_filename

        # Download the file from Telegram
        file = await context.bot.get_file(photo.file_id)
        await file.download_to_drive(str(image_path))
        logger.info("Downloaded photo to: %s", image_path)

        # Update status
        await status_msg.edit_text(
            "⏳ *Processing your photo...*\n\n"
            "✅ Step 1/3: Image downloaded\n"
            "🤖 Step 2/3: Generating AI caption...",
            parse_mode="Markdown",
        )

        # Step 2: Generate caption with Gemini
        caption = await generate_caption(str(image_path), user_caption)
        logger.info("Generated caption: %s", caption[:100])

        # Update status
        await status_msg.edit_text(
            "⏳ *Processing your photo...*\n\n"
            "✅ Step 1/3: Image downloaded\n"
            "✅ Step 2/3: Caption generated\n"
            "📸 Step 3/3: Posting to Instagram & Facebook...",
            parse_mode="Markdown",
        )

        # Step 3: Post to platforms
        # Instagram requires a public URL
        public_image_url = f"{settings.image_serve_base_url}/{image_filename}"
        logger.info("Public image URL: %s", public_image_url)

        # Run tasks (publish concurrently)
        insta_success = False
        fb_success = False
        insta_link = None
        fb_link = None
        errors = []

        # Try Instagram
        try:
            insta_result = await publish_photo(public_image_url, caption)
            insta_success = True
            insta_link = insta_result.get("permalink")
        except Exception as e:
            logger.error("Instagram publish failed: %s", e)
            errors.append(f"Instagram: {e}")

        # Try Facebook Page (URL upload)
        try:
            fb_result = await publish_to_facebook(public_image_url, caption)
            fb_success = True
            fb_link = fb_result.get("permalink")
        except Exception as e:
            logger.error("Facebook publish failed: %s", e)
            errors.append(f"Facebook: {e}")

        # Construct result message
        success_text = "🎉 *Publishing Complete!*\n\n"
        success_text += f"📝 *Caption:*\n{caption}\n\n"
        
        success_text += "📢 *Platforms:*\n"
        if insta_success:
            success_text += f"✅ *Instagram:* [View Post]({insta_link})\n" if insta_link else "✅ *Instagram:* Posted!\n"
        else:
            success_text += "❌ *Instagram:* Failed\n"

        if fb_success:
            success_text += f"✅ *Facebook Page:* [View Post]({fb_link})\n" if fb_link else "✅ *Facebook Page:* Posted!\n"
        else:
            success_text += "❌ *Facebook Page:* Failed\n"

        if errors:
            success_text += "\n⚠️ *Errors:*\n"
            for err in errors:
                success_text += f"• `{err}`\n"

        await status_msg.edit_text(success_text, parse_mode="Markdown")
        logger.info("Publishing flow complete. Insta: %s, FB: %s", insta_success, fb_success)

    except Exception as e:
        logger.error("Unexpected error in photo handler: %s", e, exc_info=True)
        await status_msg.edit_text(
            f"❌ *Something went wrong:*\n\n`{e}`\n\n"
            "Please try again or check the server logs.",
            parse_mode="Markdown",
        )

    finally:
        # Clean up temp image after a delay (keep it for Instagram to fetch)
        # Instagram needs time to download the image, so we don't delete immediately
        # The cleanup is handled by the FastAPI lifespan or a background task
        pass
