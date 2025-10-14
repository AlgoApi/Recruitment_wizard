import logging
from logging.handlers import TimedRotatingFileHandler
import os

LOG_DIR = os.getenv('LOG_DIR', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging(level: str = 'INFO'):
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = TimedRotatingFileHandler(
        os.path.join(LOG_DIR, 'bot.log'), when='midnight', backupCount=14, encoding='utf-8'
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
