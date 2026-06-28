"""Instagram Graph API publisher — handles the two-step media publishing flow."""

import asyncio
import logging
from enum import Enum

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.instagram.com"


class MediaStatus(str, Enum):
    """Possible statuses for an Instagram media container."""
    FINISHED = "FINISHED"
    IN_PROGRESS = "IN_PROGRESS"
    ERROR = "ERROR"
    EXPIRED = "EXPIRED"


class InstagramPublishError(Exception):
    """Raised when Instagram publishing fails."""
    pass


async def publish_photo(image_url: str, caption: str) -> dict:
    """
    Publish a photo to Instagram using the Graph API two-step flow.

    Args:
        image_url: Publicly accessible URL of the image.
        caption: Caption text for the post.

    Returns:
        Dict with post ID and permalink.

    Raises:
        InstagramPublishError: If any step of the publishing fails.
    """
    logger.info("Starting Instagram publish flow...")
    logger.info("Image URL: %s", image_url)
    logger.info("Caption length: %d chars", len(caption))

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Create media container
        container_id = await _create_media_container(client, image_url, caption)
        logger.info("Created media container: %s", container_id)

        # Step 2: Wait for container to be ready
        await _wait_for_container(client, container_id)
        logger.info("Container is ready for publishing")

        # Step 3: Publish the container
        post_id = await _publish_container(client, container_id)
        logger.info("Published! Post ID: %s", post_id)

        # Step 4: Get permalink (optional, may fail for some account types)
        permalink = await _get_permalink(client, post_id)

        return {
            "post_id": post_id,
            "permalink": permalink,
        }


async def publish_video(video_url: str, caption: str) -> dict:
    """
    Publish a Reel (video) to Instagram using the Graph API two-step flow.

    Args:
        video_url: Publicly accessible URL of the video.
        caption: Caption text for the Reel.

    Returns:
        Dict with post ID and permalink.

    Raises:
        InstagramPublishError: If any step of the publishing fails.
    """
    logger.info("Starting Instagram Reel publish flow...")
    logger.info("Video URL: %s", video_url)
    logger.info("Caption length: %d chars", len(caption))

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Create media container
        container_id = await _create_video_media_container(client, video_url, caption)
        logger.info("Created video media container: %s", container_id)

        # Step 2: Wait for container to be ready (longer polling for video processing)
        await _wait_for_container(client, container_id, max_retries=30, delay=5.0)
        logger.info("Video container is ready for publishing")

        # Step 3: Publish the container
        post_id = await _publish_container(client, container_id)
        logger.info("Published Reel! Post ID: %s", post_id)

        # Step 4: Get permalink
        permalink = await _get_permalink(client, post_id)

        return {
            "post_id": post_id,
            "permalink": permalink,
        }


async def _create_video_media_container(
    client: httpx.AsyncClient, video_url: str, caption: str
) -> str:
    """Create a media container for Instagram Reel/Video."""
    url = f"{GRAPH_API_BASE}/{settings.instagram_api_version}/{settings.instagram_account_id}/media"
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": settings.instagram_access_token,
    }

    response = await client.post(url, params=params)
    data = response.json()

    if "error" in data:
        error_msg = data["error"].get("message", "Unknown error")
        logger.error("Failed to create video container: %s", data["error"])
        raise InstagramPublishError(f"Video container creation failed: {error_msg}")

    container_id = data.get("id")
    if not container_id:
        raise InstagramPublishError(f"No container ID in response: {data}")

    return container_id


async def _create_media_container(
    client: httpx.AsyncClient, image_url: str, caption: str
) -> str:
    """Step 1: Create a media container with the image URL and caption."""
    url = f"{GRAPH_API_BASE}/{settings.instagram_api_version}/{settings.instagram_account_id}/media"
    params = {
        "image_url": image_url,
        "caption": caption,
        "access_token": settings.instagram_access_token,
    }

    response = await client.post(url, params=params)
    data = response.json()

    if "error" in data:
        error_msg = data["error"].get("message", "Unknown error")
        logger.error("Failed to create media container: %s", data["error"])
        raise InstagramPublishError(f"Container creation failed: {error_msg}")

    container_id = data.get("id")
    if not container_id:
        raise InstagramPublishError(f"No container ID in response: {data}")

    return container_id


async def _wait_for_container(
    client: httpx.AsyncClient, container_id: str, max_retries: int = 15, delay: float = 3.0
) -> None:
    """Wait for the media container to finish processing."""
    url = f"{GRAPH_API_BASE}/{settings.instagram_api_version}/{container_id}"
    params = {
        "fields": "status_code,status",
        "access_token": settings.instagram_access_token,
    }

    for attempt in range(max_retries):
        response = await client.get(url, params=params)
        data = response.json()

        status = data.get("status_code", "UNKNOWN")
        logger.info("Container status (attempt %d/%d): %s", attempt + 1, max_retries, status)

        if status == MediaStatus.FINISHED:
            return
        elif status == MediaStatus.ERROR:
            error_detail = data.get("status", "Unknown error")
            raise InstagramPublishError(f"Container processing failed: {error_detail}")
        elif status == MediaStatus.EXPIRED:
            raise InstagramPublishError("Container expired before publishing")

        await asyncio.sleep(delay)

    raise InstagramPublishError(f"Container not ready after {max_retries} attempts")


async def _publish_container(client: httpx.AsyncClient, container_id: str) -> str:
    """Step 2: Publish the ready media container."""
    url = f"{GRAPH_API_BASE}/{settings.instagram_api_version}/{settings.instagram_account_id}/media_publish"
    params = {
        "creation_id": container_id,
        "access_token": settings.instagram_access_token,
    }

    response = await client.post(url, params=params)
    data = response.json()

    if "error" in data:
        error_msg = data["error"].get("message", "Unknown error")
        logger.error("Failed to publish container: %s", data["error"])
        raise InstagramPublishError(f"Publishing failed: {error_msg}")

    post_id = data.get("id")
    if not post_id:
        raise InstagramPublishError(f"No post ID in response: {data}")

    return post_id


async def _get_permalink(client: httpx.AsyncClient, post_id: str) -> str | None:
    """Fetch the permalink for the published post."""
    try:
        url = f"{GRAPH_API_BASE}/{settings.instagram_api_version}/{post_id}"
        params = {
            "fields": "permalink",
            "access_token": settings.instagram_access_token,
        }

        response = await client.get(url, params=params)
        data = response.json()
        return data.get("permalink")

    except Exception as e:
        logger.warning("Could not fetch permalink: %s", e)
        return None
