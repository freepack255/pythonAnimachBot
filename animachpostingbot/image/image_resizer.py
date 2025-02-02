from PIL import Image
from io import BytesIO
from loguru import logger
import httpx

TELEGRAM_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
# Preferred dimensions for Telegram; images larger than this will be resized.
TELEGRAM_PREFERRED_MAX_DIMENSIONS = (1280, 1280)
TELEGRAM_MIN_DIMENSIONS = (200, 200)  # Minimum dimensions to avoid Telegram issues
JPEG_QUALITY = 85

async def validate_and_resize_image(url: str) -> BytesIO | None:
    headers = {"Referer": "https://www.pixiv.net/"}

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

        return output
