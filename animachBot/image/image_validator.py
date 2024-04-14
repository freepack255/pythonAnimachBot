from PIL import Image
import io
import urllib.request
import urllib3
from animachBot.logger.logger import logger


def is_image_size_acceptable(url, max_size_bytes):
    try:
        with urllib.request.urlopen(url) as response:
            content_length = response.getheader('Content-Length')
            if content_length:
                size_in_bytes = int(content_length)
                logger.info(f"Image size: {size_in_bytes} bytes")
                return size_in_bytes <= max_size_bytes
            else:
                # If Content-Length is missing, load part of the file to check its size
                data = response.read(max_size_bytes + 1)  # Read 1 byte more than the maximum allowed size
                return len(data) <= max_size_bytes
    except Exception as e:
        logger.error(f"Error determining image size: {e}")
        return False


def get_image_dimensions(url):
    num_bytes_to_read = 8192

    with urllib.request.urlopen(url) as response:
        # Read only the first 8 KB of the image
        header_data = response.read(num_bytes_to_read)

    # Use BytesIO to simulate a file object
    img_file_like = io.BytesIO(header_data)

    # Open the image using PIL
    try:
        with Image.open(img_file_like) as img:
            width, height = img.size
            logger.info(f"Image dimensions: {width}x{height}")
            return width, height
    except IOError:
        # If PIL cannot open the image, return None
        logger.error("Failed to open image with PIL.")
        return None


class ImageValidator:
    def __init__(self, max_width=1200, max_height=1200, max_size_bytes=10 * 1024 * 1024):
        self.max_width = max_width
        self.max_height = max_height
        self.max_size_bytes = max_size_bytes

    def is_valid_image(self, url):
        dimensions = get_image_dimensions(url)
        if dimensions is None:
            return False

        width, height = dimensions
        if width > self.max_width or height > self.max_height:
            logger.info(f"Image dimensions exceed the maximum allowed size. Width: {width}, Height: {height}")
            return False

        if not is_image_size_acceptable(url, self.max_size_bytes):
            logger.info(f"Image size exceeds the maximum allowed size. URL: {url}")
            return False

        return True


class PixivMediaMixin(object):
    url: str
    origin_url: str
    _urllib3_headers_for_web_image = {}

    def convert_from_rsshub_to_pixiv_image(self) -> None:
        netloc = urllib3.util.parse_url(self.url).netloc
        if netloc == "i.pximg.net":
            logger.info(msg=f"Image's URL is already converted to i.pximg.net")
            return None
        elif netloc != "pixiv.rsshub.app":
            raise ValueError(f"Other sources rather than Pixiv.rsshub.app are not supported for {self.url}")

        self.origin_url = self.url
        self.url = self.url.replace('pixiv.rsshub.app', 'i.pximg.net')
        self._urllib3_headers_for_web_image.update({"Referer": "https://www.pixiv.net/"})
