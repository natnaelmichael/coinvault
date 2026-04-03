"""
Logging Utility
Centralized logging configuration for the pump.fun bot
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from .config import config


class BotLogger:
    """Custom logger for the pump.fun bot"""
    
    _instance: Optional['BotLogger'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.logger = logging.getLogger("PumpFunBot")
        self.logger.setLevel(getattr(logging, config.log_level, logging.INFO))
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        # Console handler (always active)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler (if enabled)
        if config.log_to_file:
            self._setup_file_handler()
        
        self._initialized = True
    
    def _setup_file_handler(self):
        """Setup file logging handler"""
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"pumpfun_bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        self.logger.info(f"Logging to file: {log_file}")
    
    def debug(self, message: str):
        """Log debug message"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """Log info message"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """Log warning message"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """Log error message"""
        self.logger.error(message)
    
    def critical(self, message: str):
        """Log critical message"""
        self.logger.critical(message)
    
    def trade(self, message: str):
        """Log trade-related message (always shown)"""
        self.logger.info(f"[TRADE] {message}")
    
    def alert(self, message: str):
        """Log alert message (always shown)"""
        self.logger.warning(f"[ALERT] {message}")


# Global logger instance
logger = BotLogger()
