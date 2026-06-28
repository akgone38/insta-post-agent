"""Facebook Page API publisher — publishes photos directly to Facebook Pages."""

import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com"


class FacebookPublishError(Exception):
    """Raised when Facebook page publishing fails."""
    pass


async def publish_to_facebook(image_url: str, caption: str) -> dict:
    """
    Publish a photo to Facebook Page using the public image URL.

    Args:
        image_url: Publicly accessible URL of the image.
        caption: Caption/message text for the post.

    Returns:
        Dict with post ID and permalink.

    Raises:
        FacebookPublishError: If publishing fails.
    """
    logger.info("Starting Facebook Page publish flow...")
    logger.info("Image URL: %s", image_url)

    url = f"{GRAPH_API_BASE}/{settings.instagram_api_version}/{settings.facebook_page_id}/photos"
    
    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": settings.facebook_page_access_token,
        "published": "true",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, data=payload)
                
            data = response.json()
            
            if "error" in data:
                error_msg = data["error"].get("message", "Unknown error")
                logger.error("Failed to post to Facebook: %s", data["error"])
                raise FacebookPublishError(f"Facebook posting failed: {error_msg}")
                
            post_id = data.get("id")
            post_key = data.get("post_id")  # Sometimes returned as post_id depending on version
            
            final_post_id = post_key or post_id
            
            logger.info("Facebook post created! ID: %s", final_post_id)
            
            # Construct a permalink
            permalink = f"https://www.facebook.com/{final_post_id}"
            
            return {
                "post_id": final_post_id,
                "permalink": permalink,
            }

    except Exception as e:
        if not isinstance(e, FacebookPublishError):
            logger.error("Unexpected error posting to Facebook: %s", e)
            raise FacebookPublishError(f"Unexpected error: {e}") from e
        raise
