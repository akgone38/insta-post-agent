"""Telegram message handlers — orchestrates the full pipeline."""

import logging
import uuid
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings
from app.ai.caption_gen import generate_caption
from app.instagram.publisher import publish_photo, publish_video, InstagramPublishError
from app.facebook.publisher import publish_to_facebook, publish_video_to_facebook, FacebookPublishError

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


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming photos and videos — the main pipeline.

    Flow:
    1. Download the media (photo or video) from Telegram
    2. Generate an engaging caption using Hugging Face (Llama Vision)
    3. Upload concurrently to Instagram (Image or Reel) and Facebook (Photo or Video)
    4. Reply with post links
    """
    message = update.message
    user = message.from_user
    
    # Determine media type
    is_video = bool(message.video)
    media_name = "video" if is_video else "photo"
    logger.info("Received %s from user %s (%s)", media_name, user.username, user.id)

    # Send "processing" status
    status_msg = await message.reply_text(
        f"⏳ *Processing your {media_name}...*\n\n"
        f"🔍 Step 1/3: Downloading {media_name}...",
        parse_mode="Markdown",
    )

    try:
        # Step 1: Download the file (highest resolution)
        user_caption = message.caption
        file_id = str(uuid.uuid4())[:8]
        
        if is_video:
            video = message.video
            file_extension = Path(video.file_name or "video.mp4").suffix or ".mp4"
            media_filename = f"{file_id}{file_extension}"
            telegram_file_id = video.file_id
        else:
            photo = message.photo[-1]  # Highest resolution photo
            media_filename = f"{file_id}.jpg"
            telegram_file_id = photo.file_id

        media_path = TEMP_IMAGE_DIR / media_filename

        # Download the file from Telegram
        file = await context.bot.get_file(telegram_file_id)
        await file.download_to_drive(str(media_path))
        logger.info("Downloaded %s to: %s", media_name, media_path)

        # Update status
        await status_msg.edit_text(
            f"⏳ *Processing your {media_name}...*\n\n"
            f"✅ Step 1/3: {media_name.capitalize()} downloaded\n"
            "🤖 Step 2/3: Generating AI caption...",
            parse_mode="Markdown",
        )

        # Step 2: Generate caption using Hugging Face Llama Vision
        caption = await generate_caption(str(media_path), user_caption)
        logger.info("Generated caption: %s", caption[:100])

        # Update status
        await status_msg.edit_text(
            f"⏳ *Processing your {media_name}...*\n\n"
            f"✅ Step 1/3: {media_name.capitalize()} downloaded\n"
            "✅ Step 2/3: Caption generated\n"
            "📸 Step 3/3: Posting to Instagram & Facebook...",
            parse_mode="Markdown",
        )

        # Step 3: Post to platforms
        # Both platforms require a public URL
        public_media_url = f"{settings.image_serve_base_url}/{media_filename}"
        logger.info("Public media URL: %s", public_media_url)

        # Publish concurrently
        insta_success = False
        fb_success = False
        insta_link = None
        fb_link = None
        errors = []

        # Try Instagram (Photo vs Reel)
        try:
            if is_video:
                insta_result = await publish_video(public_media_url, caption)
            else:
                insta_result = await publish_photo(public_media_url, caption)
            insta_success = True
            insta_link = insta_result.get("permalink")
        except Exception as e:
            logger.error("Instagram publish failed: %s", e)
            errors.append(f"Instagram: {e}")

        # Try Facebook Page (Photo vs Video)
        try:
            if is_video:
                fb_result = await publish_video_to_facebook(public_media_url, caption)
            else:
                fb_result = await publish_to_facebook(public_media_url, caption)
            fb_success = True
            fb_link = fb_result.get("permalink")
        except Exception as e:
            logger.error("Facebook publish failed: %s", e)
            errors.append(f"Facebook: {e}")

        # Construct final result message
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
        logger.error("Unexpected error in media handler: %s", e, exc_info=True)
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
