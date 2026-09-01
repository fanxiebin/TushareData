"""
TushareData 统一日志配置模块
使用loguru替代print，支持分级日志和文件输出
"""

import sys
from loguru import logger

from conf_ts.dirs_config import dir_root

# logs目录挂在工作区根目录下
logs_dir = dir_root / 'logs'

# 确保logs目录存在
logs_dir.mkdir(exist_ok=True)

# 移除默认的logger配置
logger.remove()

# 自定义日志格式
console_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <level>{message}</level>"
file_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>"

# 添加控制台输出
logger.add(
    sys.stdout,
    format=console_format,
    level="INFO",
    colorize=True,
    backtrace=True,
    diagnose=True
)

# 添加文件输出
logger.add(
    logs_dir / "app.log",
    format=file_format,
    level="DEBUG",
    rotation="00:00",
    retention="30 days",
    backtrace=True,
    diagnose=True
)

def get_logger(name: str = ""):
    """
    获取logger实例

    Args:
        name: 模块名称，通常使用__name__

    Returns:
        logger实例
    """
    if not name:
        name = __name__
    return logger.bind(name=name)
