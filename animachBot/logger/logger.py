import logging

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

logging.basicConfig(
    format=FORMAT,
    level=logging.WARNING
)

logger = logging.getLogger('animachBot')
