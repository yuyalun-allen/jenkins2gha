import logging
import os
from colorlog import ColoredFormatter


def setup_logging(log_file="logs/app.log", log_level=logging.DEBUG):
    # 获取 logger
    logger = logging.getLogger(__name__)

    # 检查是否已经存在 handler，避免重复添加
    if not logger.handlers:
        # 设置日志级别
        logger.setLevel(log_level)

        # 定义控制台日志格式和颜色
        console_formatter = ColoredFormatter(
            "%(log_color)s%(levelname)s: %(message)s",
            # 在日志级别中添加颜色
            log_colors={
                'DEBUG': 'cyan',  # DEBUG 日志显示青色
                'INFO': 'green',  # INFO 日志显示绿色
                'WARNING': 'yellow',  # WARNING 日志显示黄色
                'ERROR': 'red',  # ERROR 日志显示红色
                'CRITICAL': 'bold_red'  # CRITICAL 日志显示加粗红色
            }
        )

        # 创建控制台日志处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # 如果指定了日志文件，则添加文件处理器
        if log_file:
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)

            # 为文件创建一个普通格式的日志格式（不需要颜色）
            file_formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )

            # 创建文件日志处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

    return logger
