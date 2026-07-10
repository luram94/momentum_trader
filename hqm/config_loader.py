"""
Configuration Loader Module
============================
Loads and validates configuration from config.yaml file.
Provides type-safe access to configuration values.

Every field defined here is read somewhere in the application; unknown keys
in config.yaml are ignored and missing keys fall back to these defaults, so
older config files keep loading.
"""

from __future__ import annotations

import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, fields

# Repository root (this file lives in hqm/, one level below the root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default configuration path
CONFIG_PATH = PROJECT_ROOT / 'config.yaml'


@dataclass
class PortfolioConfig:
    """Portfolio configuration settings."""
    default_size: float = 10000
    default_positions: int = 8
    min_size: float = 1000
    max_positions: int = 50


@dataclass
class DataConfig:
    """Data collection configuration."""
    exchanges: List[str] = field(default_factory=lambda: ['NYSE', 'NASDAQ'])
    min_market_cap: str = '+Mid (over $2bln)'
    cache_expiry_hours: int = 24


@dataclass
class StrategyConfig:
    """HQM strategy configuration (shared by scanner and backtest)."""
    min_percentile_threshold: int = 25


@dataclass
class ScannerFiltersConfig:
    """Default UI values for the scanner's opt-in technical filters."""
    max_sma10_distance: float = 15
    min_rsi: int = 0
    max_rsi: int = 70
    min_avg_volume: int = 500000
    max_atr_percent: float = 10
    max_per_sector: int = 3


@dataclass
class RiskConfig:
    """Risk metrics configuration."""
    benchmark: str = 'SPY'
    risk_free_rate: float = 0.05
    sharpe_period_days: int = 252


@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    default_period_days: int = 90
    initial_capital: float = 10000
    rebalance_frequency: str = 'weekly'
    slippage_percent: float = 0.1
    commission_per_trade: float = 0


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = 'INFO'
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    file: str = 'logs/hqm_scanner.log'
    max_size_mb: int = 10
    backup_count: int = 3
    console_output: bool = True


@dataclass
class RateLimitsConfig:
    """API rate limiting configuration."""
    yfinance_batch_size: int = 50


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = 'data/hqm_data.db'


@dataclass
class Config:
    """Main configuration class containing all settings."""
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    data: DataConfig = field(default_factory=DataConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    scanner_filters: ScannerFiltersConfig = field(default_factory=ScannerFiltersConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    rate_limits: RateLimitsConfig = field(default_factory=RateLimitsConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


# Section name -> dataclass for each top-level config.yaml section
_SECTIONS: Dict[str, type] = {
    'portfolio': PortfolioConfig,
    'data': DataConfig,
    'strategy': StrategyConfig,
    'scanner_filters': ScannerFiltersConfig,
    'risk': RiskConfig,
    'backtest': BacktestConfig,
    'logging': LoggingConfig,
    'rate_limits': RateLimitsConfig,
    'database': DatabaseConfig,
}


def _section_from_dict(data: Optional[Dict[str, Any]], cls: type) -> Any:
    """Build a flat section dataclass from a dict, ignoring unknown keys."""
    if not data:
        return cls()
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in known})


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file. Uses default if not specified.

    Returns:
        Config object with all settings.
    """
    path = config_path or CONFIG_PATH

    if not path.exists():
        logging.warning(f"Config file not found at {path}, using defaults")
        return Config()

    try:
        with open(path, 'r') as f:
            raw_config = yaml.safe_load(f) or {}

        return Config(**{
            name: _section_from_dict(raw_config.get(name), cls)
            for name, cls in _SECTIONS.items()
        })

    except Exception as e:
        logging.error(f"Failed to load config from {path}: {e}")
        return Config()


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
