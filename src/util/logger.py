import logging
from sys import stderr

logger = logging.getLogger("barkueue")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=stderr,
    level=logging.DEBUG,
)
