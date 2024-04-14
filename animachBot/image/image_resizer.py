import os
import shutil
import tempfile
from PIL import Image
import io
import urllib.request
from animachBot.logger.logger import logger


class ImageResizer:
    def __init__(self, target_width=1200, target_height=1200, max_size_bytes=10 * 1024 * 1024):
        self.target_width = target_width
        self.target_height = target_height
        self.max_size_bytes = max_size_bytes
        self.temp_dir = tempfile.mkdtemp()

    def resize_image(self, url):
        try:
            with urllib.request.urlopen(url) as response:
                image_data = response.read()
            image = Image.open(io.BytesIO(image_data))
        except Exception as e:
            logger.error(f"Failed to download or open image: {e}")
            return None

        # Resize the image
        image = image.resize((self.target_width, self.target_height), Image.Resampling.LANCZOS)

        # Save the resized image to the temporary directory
        image_name = os.path.basename(url)
        temp_image_path = os.path.join(self.temp_dir, image_name)
        image.save(temp_image_path)

        # Check the size of the resized image
        file_size = os.path.getsize(temp_image_path)
        if file_size > self.max_size_bytes:
            logger.info(f"Resized image exceeds the maximum allowed size of {self.max_size_bytes} bytes.")
            os.remove(temp_image_path)  # Remove the file if it exceeds the size limit
            return None

        logger.info(f"Resized image saved to: {temp_image_path}")
        return temp_image_path

    def clean_up(self):
        # Delete the temporary directory and all its contents
        shutil.rmtree(self.temp_dir)
        logger.info("Temporary directory cleaned up.")
