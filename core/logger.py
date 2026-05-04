import logging
import os
from logging.handlers import RotatingFileHandler

from core.tracing import current_trace_id


CONSOLE_HANDLER_NAME = "friday_console"
FILE_HANDLER_NAME = "friday_file"


class _TraceContextFilter(logging.Filter):
    """Inject the current trace_id into every LogRecord.

    The contextvar is read lazily per record, so the same logger works
    correctly across threads (each thread sees its own bound trace_id).
    Records emitted outside a turn render trace_id as a single dash.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # extra={"trace_id": ...} on a specific call wins over the contextvar
        existing = getattr(record, "trace_id", None)
        if not existing:
            record.trace_id = current_trace_id() or "-"
        return True


import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def setup_logger(name="FRIDAY"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(module)s] [trace=%(trace_id)s] %(message)s'
        )

        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'friday.log'),
            maxBytes=5*1024*1024,
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.set_name(FILE_HANDLER_NAME)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.set_name(CONSOLE_HANDLER_NAME)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Filter goes on the logger so it covers handlers added later too.
        logger.addFilter(_TraceContextFilter())

    return logger


def set_console_logging(enabled: bool, level=logging.INFO, name="FRIDAY"):
    logger = logging.getLogger(name)
    for handler in logger.handlers:
        if handler.get_name() == CONSOLE_HANDLER_NAME:
            handler.setLevel(level if enabled else logging.CRITICAL + 1)
            break


# Global logger instance
logger = setup_logger()
