import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name="FRIDAY"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Prevent adding handlers multiple times if instantiated repeatedly
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(module)s] %(message)s'
        )

        # Ensure logs directory exists
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # File Handler (Rotating)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'friday.log'),
            maxBytes=5*1024*1024, # 5MB
            backupCount=3
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

# Global logger instance
logger = setup_logger()
