# app/core/logger.py
import logging
import sys
from loguru import logger  # Рекомендую loguru - проще и мощнее стандартного logging

# Настройка loguru
logger.remove()  # Убираем дефолтный handler
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)


# Для совместимости со стандартным logging (если нужно)
class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Получаем соответствующий уровень loguru
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Находием caller
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


# Альтернатива: простой стандартный логгер
def setup_logger():
    """Простая настройка стандартного логгера"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('app.log')  # Опционально: логи в файл
        ]
    )
    return logging.getLogger(__name__)