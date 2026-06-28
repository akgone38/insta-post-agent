"""AI-powered caption generation using Hugging Face Inference API with Llama Vision."""

import asyncio
import base64
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# System prompt tailored for State Park RV Village
SYSTEM_PROMPT = """You are a social media manager for **State Park RV Village**, a brand new, 
premium 44-site long-term RV Park located in Lockhart, TX (just 30 minutes from Austin).

Your job is to write engaging Instagram captions that will attract organic followers and 
drive bookings. The target audience is RV owners, full-time RVers, traveling families, 
retirees, and outdoor enthusiasts looking for long-term stays near Austin.

**Brand Voice:**
- Warm, welcoming, and community-focused
- Emphasize the peaceful, spacious, and nature-oriented experience
- Highlight proximity to Austin, Lockhart (BBQ capital of Texas!), and nearby state parks
- Mention current specials when appropriate (e.g., "$150 off first 2 months rent")

**Caption Guidelines:**
- Start with an attention-grabbing hook (question, bold statement, or emoji)
- Keep the main caption 2-4 sentences — concise but compelling
- Include a clear call-to-action (CTA): "Link in bio", "DM us", "Book your spot today"
- Add a line break, then include 15-20 relevant hashtags
- Use emojis naturally but don't overdo it (3-5 per caption)

**Hashtag Bank (use a mix of these + any relevant ones):**
#RVLife #RVPark #RVLiving #FullTimeRV #RVTravel #TexasRVing 
#LockhartTX #AustinTX #TexasCamping #RVCommunity #LongTermRV
#StateParkRVVillage #RVLifestyle #CampingLife #RoadTrip
#TexasTravel #OutdoorLiving #RVHome #RVAdventures #RVParkLife

**Important:** Analyze the image provided and write a caption that is specifically relevant 
to what's shown in the photo. Don't write generic captions — be specific to the visual content.

Return ONLY the caption text (no extra explanation, no quotes around it)."""


def _extract_first_frame(video_path: str) -> str:
    """
    Extract the first frame of a video using OpenCV and save it as a temp JPG.
    
    Returns the path to the temp JPG image.
    """
    import cv2
    logger.info("Extracting first frame from video: %s", video_path)
    vidcap = cv2.VideoCapture(video_path)
    success, image = vidcap.read()
    if not success:
        vidcap.release()
        raise RuntimeError(f"Could not read video frames from {video_path}")
        
    temp_jpg_path = video_path + ".frame0.jpg"
    cv2.imwrite(temp_jpg_path, image)
    vidcap.release()
    logger.info("Successfully extracted first frame to: %s", temp_jpg_path)
    return temp_jpg_path


async def generate_caption(image_path: str, user_note: str | None = None) -> str:
    """
    Generate an engaging Instagram caption by analyzing the image (or video frame) with Llama Vision.

    Uses Hugging Face Inference API with multimodal models.
    Includes retry logic and fallback models.

    Args:
        image_path: Path to the image (or video) file on disk.
        user_note: Optional note/context from the user to incorporate.

    Returns:
        Generated caption string ready for Instagram.
    """
    logger.info("Generating caption for media: %s", image_path)

    # Check if media is a video
    is_video = Path(image_path).suffix.lower() in [".mp4", ".mov", ".avi", ".mkv", ".3gp"]
    temp_frame_path = None
    
    try:
        if is_video:
            temp_frame_path = _extract_first_frame(image_path)
            model_image_path = temp_frame_path
        else:
            model_image_path = image_path

        # Read image and encode as base64
        image_data = Path(model_image_path).read_bytes()
        mime_type = _get_mime_type(model_image_path)
        image_b64 = base64.b64encode(image_data).decode("utf-8")
        image_url = f"data:{mime_type};base64,{image_b64}"

        # Build user prompt
        user_prompt = "Write an engaging Instagram caption for this image."
        if user_note:
            user_prompt += f"\n\nAdditional context from the user: {user_note}"

        # Build chat messages (OpenAI-compatible format used by HF)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                    {
                        "type": "text",
                        "text": user_prompt,
                    },
                ],
            },
        ]

        last_error = None

        for model_name in settings.vision_models_list:
            for attempt in range(3):
                try:
                    logger.info("Trying model: %s (attempt %d/3)", model_name, attempt + 1)

                    caption = await _call_hf_inference(model_name, messages)

                    logger.info(
                        "Generated caption with %s (%d chars): %s...",
                        model_name, len(caption), caption[:100],
                    )
                    return caption

                except Exception as e:
                    last_error = e
                    error_str = str(e)

                    if "429" in error_str or "rate" in error_str.lower():
                        wait_time = 10 * (attempt + 1)
                        logger.warning(
                            "Rate limited on %s (attempt %d). Waiting %ds...",
                            model_name, attempt + 1, wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    elif "503" in error_str or "loading" in error_str.lower():
                        wait_time = 20 * (attempt + 1)
                        logger.warning(
                            "Model %s is loading (attempt %d). Waiting %ds...",
                            model_name, attempt + 1, wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error("Error with %s: %s", model_name, e)
                        break  # Try next model

            logger.warning("All retries exhausted for %s, trying next model...", model_name)

        raise RuntimeError(f"Caption generation failed on all models: {last_error}")

    finally:
        # Clean up temp frame if it was created
        if temp_frame_path and Path(temp_frame_path).exists():
            try:
                Path(temp_frame_path).unlink()
                logger.info("Cleaned up temporary video frame: %s", temp_frame_path)
            except Exception as e:
                logger.warning("Could not delete temp video frame %s: %s", temp_frame_path, e)


async def _call_hf_inference(model_name: str, messages: list) -> str:
    """Call HF Inference API using the router endpoint with chat completion format."""
    url = f"{settings.huggingface_api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.huggingface_api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.8,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            error_text = response.text
            logger.error("HF API error (%d): %s", response.status_code, error_text[:300])
            raise RuntimeError(
                f"HF API error {response.status_code}: {error_text[:200]}"
            )

        data = response.json()
        caption = data["choices"][0]["message"]["content"].strip()
        return caption


def _get_mime_type(file_path: str) -> str:
    """Determine MIME type from file extension."""
    ext = Path(file_path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mime_map.get(ext, "image/jpeg")
