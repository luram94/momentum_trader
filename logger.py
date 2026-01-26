"""
Logging Module
===============
Centralized logging configuration for the HQM Momentum Scanner.
Provides structured logging with file rotation and console output.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Logger cache
_loggers: dict[str, logging.Logger] = {}


def setup_logging(
    name: str = 'hqm',
    level: str = 'INFO',
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    max_size_mb: int = 10,
    backup_count: int = 3,
    console_output: bool = True
) -> logging.Logger:
    """
    Set up and configure a logger with file and console handlers.

    Args:
        name: Logger name (module name)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file. None for no file logging.
        log_format: Custom log format string
        max_size_mb: Maximum log file size in MB before rotation
        backup_count: Number of backup files to keep
        console_output: Whether to output to console

    Returns:
        Configured logger instance
    """
    # Return cached logger if already configured
    if name in _loggers:
        return _loggers[name]

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False

    # Clear existing handlers
    logger.handlers.clear()

    # Default format
    if log_format is None:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    formatter = logging.Formatter(log_format)

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        log_path = Path(__file__).parent / log_file
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.addHandler(file_handler)

    # Cache the logger
    _loggers[name] = logger

    return logger


def get_logger(name: str = 'hqm') -> logging.Logger:
    """
    Get a logger instance. Creates one if it doesn't exist.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    if name in _loggers:
        return _loggers[name]

    # Try to load config for default settings
    try:
        from config_loader import get_config
        config = get_config()
        return setup_logging(
            name=name,
            level=config.logging.level,
            log_file=config.logging.file,
            log_format=config.logging.format,
            max_size_mb=config.logging.max_size_mb,
            backup_count=config.logging.backup_count,
            console_output=config.logging.console_output
        )
    except ImportError:
        # Fallback to basic setup
        return setup_logging(name=name)


class LoggerMixin:
    """
    Mixin class that provides logging capability to any class.

    Usage:
        class MyClass(LoggerMixin):
            def my_method(self):
                self.logger.info("Doing something")
    """

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        if not hasattr(self, '_logger'):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger


# Convenience functions for module-level logging
def debug(msg: str, *args, **kwargs) -> None:
    """Log a debug message."""
    get_logger().debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs) -> None:
    """Log an info message."""
    get_logger().info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs) -> None:
    """Log a warning message."""
    get_logger().warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs) -> None:
    """Log an error message."""
    get_logger().error(msg, *args, **kwargs)


def critical(msg: str, *args, **kwargs) -> None:
    """Log a critical message."""
    get_logger().critical(msg, *args, **kwargs)


def exception(msg: str, *args, **kwargs) -> None:
    """Log an exception with traceback."""
    get_logger().exception(msg, *args, **kwargs)
