import logging
import os
from logging.handlers import RotatingFileHandler


CONSOLE_HANDLER_NAME = "friday_console"
FILE_HANDLER_NAME = "friday_file"


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
        file_handler.set_name(FILE_HANDLER_NAME)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.set_name(CONSOLE_HANDLER_NAME)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def set_console_logging(enabled: bool, level=logging.INFO, name="FRIDAY"):
    logger = logging.getLogger(name)
    for handler in logger.handlers:
        if handler.get_name() == CONSOLE_HANDLER_NAME:
            handler.setLevel(level if enabled else logging.CRITICAL + 1)
            break

# Global logger instance
logger = setup_logger()
