from io import BytesIO

import httpx
from PIL import Image
from loguru import logger

from animachpostingbot.config.config import NSFW_DETECTOR_URL, NSFW_THRESHOLD

TELEGRAM_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
# Preferred dimensions for Telegram; images larger than this will be resized.
TELEGRAM_PREFERRED_MAX_DIMENSIONS = (1280, 1280)
TELEGRAM_MIN_DIMENSIONS = (200, 200)  # Minimum dimensions to avoid Telegram issues
JPEG_QUALITY = 85

def get_headers(url: str) -> dict:
    """
    Returns appropriate HTTP headers based on the source of the image.
    For example, for Pixiv images, a Referer is required.
    For Twitter images, a different referer might be needed.
    """
    if "pixiv.net" in url or "pximg.net" in url or "i.pixiv.re" in url or "pixiv" in url:
        return {"Referer": "https://www.pixiv.net/"}
    elif "twitter.com" in url or "x.com" in url:
        return {"Referer": "https://twitter.com/"}
    else:
        return {}

async def check_nsfw(image_data: bytes) -> dict:
    """
    Sends the image data to the NSFW detector and returns the JSON result.
    It is expected that the detector returns a JSON with a "result" key containing an "nsfw" probability.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": ("image.jpg", image_data, "image/jpeg")}
            response = await client.post(f"{NSFW_DETECTOR_URL}/check", files=files)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"NSFW detector returned: {result}")
            return result
    except Exception as e:
        logger.error(f"Error during NSFW detection: {e}")
        return {}  # Return an empty dictionary in case of error

async def validate_and_resize_image(url: str) -> BytesIO | None:
    """
    Fetches an image from the given URL, resizes it if necessary,
    and returns a BytesIO object containing the processed image.
    Also sends the image data to the NSFW detector; if the NSFW score is above the threshold,
    the image is skipped.
    """
    headers = get_headers(url)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            logger.debug(f"Successfully fetched image from {url}")
        except httpx.HTTPError as e:
            logger.error(f"Error fetching image from {url}: {e}")
            return None

        try:
            img = Image.open(BytesIO(response.content))
            logger.debug(f"Opened image from {url} with mode: {img.mode}")
        except Exception as e:
            logger.error(f"Error opening image from {url}: {e}")
            return None

        width, height = img.size
        logger.info(f"Fetched image {url} with dimensions: {width}x{height}")

        if width < TELEGRAM_MIN_DIMENSIONS[0] or height < TELEGRAM_MIN_DIMENSIONS[1]:
            logger.warning(f"Skipping image {url}: Too small ({width}x{height})")
            return None

        # Resize if the image is larger than preferred dimensions.
        if width > TELEGRAM_PREFERRED_MAX_DIMENSIONS[0] or height > TELEGRAM_PREFERRED_MAX_DIMENSIONS[1]:
            img.thumbnail(TELEGRAM_PREFERRED_MAX_DIMENSIONS, Image.LANCZOS)
            logger.info(f"Resized image {url} to fit within {TELEGRAM_PREFERRED_MAX_DIMENSIONS}")
            logger.debug(f"New dimensions: {img.size[0]}x{img.size[1]}")

        # Convert image mode if necessary.
        if img.mode in ("LA", "P"):
            logger.debug(f"Image {url} has mode {img.mode}; converting to RGB for JPEG compatibility")
            img = img.convert("RGB")
            logger.debug(f"Converted image mode: {img.mode}")

        output = BytesIO()
        # Use JPEG if possible; if image mode is RGBA, use PNG.
        img_format = "JPEG" if img.mode != "RGBA" else "PNG"
        try:
            img.save(output, format=img_format, quality=JPEG_QUALITY, optimize=True)
            logger.debug(f"Saved image {url} as {img_format} with quality {JPEG_QUALITY}")
        except Exception as e:
            logger.error(f"Error saving image {url}: {e}")
            return None
        output.seek(0)

        final_size = output.getbuffer().nbytes
        logger.info(f"Processed image {url}: final size {final_size/1024:.2f} KB")
        if final_size > TELEGRAM_MAX_FILE_SIZE:
            logger.warning(f"Skipping image {url}: File too large after compression ({final_size/1024:.2f} KB)")
            return None

        # NSFW detection: send image to the local NSFW detector.
        nsfw_result = await check_nsfw(output.getvalue())
        logger.info(f"NSFW detector result for {url}: {nsfw_result}")
        # Check the nested value under 'result'
        if nsfw_result.get("result", {}).get("nsfw", 0) > NSFW_THRESHOLD:
            logger.warning(f"Image {url} flagged as NSFW: {nsfw_result}. Skipping this image.")
            return None

        return output
