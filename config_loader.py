"""
Configuration Loader Module
============================
Loads and validates configuration from config.yaml file.
Provides type-safe access to configuration values.
"""

from __future__ import annotations

import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

# Default configuration path
CONFIG_PATH = Path(__file__).parent / 'config.yaml'


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
    """HQM strategy configuration."""
    min_percentile_threshold: int = 25
    timeframes: List[str] = field(default_factory=lambda: ['1M', '3M', '6M', '1Y'])


@dataclass
class SMAConfig:
    """SMA indicator configuration."""
    period: int = 10
    good_threshold: float = 5
    moderate_threshold: float = 15


@dataclass
class RSIConfig:
    """RSI indicator configuration."""
    enabled: bool = True
    period: int = 14
    overbought: float = 70
    oversold: float = 30


@dataclass
class VolumeConfig:
    """Volume indicator configuration."""
    enabled: bool = True
    min_avg_volume: int = 500000
    volume_surge_threshold: float = 1.5


@dataclass
class VolatilityConfig:
    """Volatility configuration."""
    enabled: bool = True
    atr_period: int = 14
    max_atr_percent: float = 10


@dataclass
class IndicatorsConfig:
    """Technical indicators configuration."""
    sma: SMAConfig = field(default_factory=SMAConfig)
    rsi: RSIConfig = field(default_factory=RSIConfig)
    volume: VolumeConfig = field(default_factory=VolumeConfig)
    volatility: VolatilityConfig = field(default_factory=VolatilityConfig)


@dataclass
class SectorDiversificationConfig:
    """Sector diversification settings."""
    enabled: bool = True
    max_per_sector: int = 3


@dataclass
class SectorsConfig:
    """Sector configuration."""
    diversification: SectorDiversificationConfig = field(default_factory=SectorDiversificationConfig)
    excluded_sectors: List[str] = field(default_factory=list)


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
    include_dividends: bool = False
    slippage_percent: float = 0.1
    commission_per_trade: float = 0



@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = 'INFO'
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    file: str = 'hqm_scanner.log'
    max_size_mb: int = 10
    backup_count: int = 3
    console_output: bool = True


@dataclass
class RateLimitsConfig:
    """API rate limiting configuration."""
    finviz_delay_seconds: float = 1
    yfinance_batch_size: int = 50
    max_retries: int = 3
    retry_delay_seconds: float = 5


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = 'hqm_data.db'
    vacuum_on_startup: bool = False


@dataclass
class Config:
    """Main configuration class containing all settings."""
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    data: DataConfig = field(default_factory=DataConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    indicators: IndicatorsConfig = field(default_factory=IndicatorsConfig)
    sectors: SectorsConfig = field(default_factory=SectorsConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    rate_limits: RateLimitsConfig = field(default_factory=RateLimitsConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


def _dict_to_dataclass(data: Dict[str, Any], cls: type) -> Any:
    """Recursively convert a dictionary to a dataclass instance."""
    if data is None:
        return cls()

    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}

    for key, value in data.items():
        if key in field_types:
            field_type = field_types[key]
            # Check if field type is a dataclass
            if hasattr(field_type, '__dataclass_fields__'):
                kwargs[key] = _dict_to_dataclass(value, field_type)
            else:
                kwargs[key] = value

    return cls(**kwargs)


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

        # Build config object from raw data
        config = Config(
            portfolio=_dict_to_dataclass(raw_config.get('portfolio', {}), PortfolioConfig),
            data=_dict_to_dataclass(raw_config.get('data', {}), DataConfig),
            strategy=_dict_to_dataclass(raw_config.get('strategy', {}), StrategyConfig),
            indicators=IndicatorsConfig(
                sma=_dict_to_dataclass(raw_config.get('indicators', {}).get('sma', {}), SMAConfig),
                rsi=_dict_to_dataclass(raw_config.get('indicators', {}).get('rsi', {}), RSIConfig),
                volume=_dict_to_dataclass(raw_config.get('indicators', {}).get('volume', {}), VolumeConfig),
                volatility=_dict_to_dataclass(raw_config.get('indicators', {}).get('volatility', {}), VolatilityConfig),
            ),
            sectors=SectorsConfig(
                diversification=_dict_to_dataclass(
                    raw_config.get('sectors', {}).get('diversification', {}),
                    SectorDiversificationConfig
                ),
                excluded_sectors=raw_config.get('sectors', {}).get('excluded_sectors', []),
            ),
            risk=_dict_to_dataclass(raw_config.get('risk', {}), RiskConfig),
            backtest=_dict_to_dataclass(raw_config.get('backtest', {}), BacktestConfig),
            logging=_dict_to_dataclass(raw_config.get('logging', {}), LoggingConfig),
            rate_limits=_dict_to_dataclass(raw_config.get('rate_limits', {}), RateLimitsConfig),
            database=_dict_to_dataclass(raw_config.get('database', {}), DatabaseConfig),
        )

        return config

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


def reload_config() -> Config:
    """Reload configuration from file."""
    global _config
    _config = load_config()
    return _config
