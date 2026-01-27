"""
Backtesting Module
===================
Simulate historical performance of HQM strategy.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from logger import get_logger
from config_loader import get_config
from database import get_connection
from risk_metrics import calculate_sharpe_ratio, calculate_max_drawdown

logger = get_logger('backtest')
config = get_config()


class BacktestEngine:
    """
    Engine for backtesting the HQM momentum strategy.
    """

    def __init__(
        self,
        initial_capital: float = 10000,
        num_positions: int = 8,
        rebalance_frequency: str = 'weekly',
        slippage_pct: float = 0.1,
        commission: float = 0
    ):
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting capital
            num_positions: Number of positions in portfolio
            rebalance_frequency: 'daily', 'weekly', or 'monthly'
            slippage_pct: Slippage as percentage of price
            commission: Commission per trade in dollars
        """
        self.initial_capital = initial_capital
        self.num_positions = num_positions
        self.rebalance_frequency = rebalance_frequency
        self.slippage_pct = slippage_pct / 100
        self.commission = commission

        self.trades: List[Dict[str, Any]] = []
        self.portfolio_history: List[Dict[str, Any]] = []
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.cash = initial_capital

    def _get_rebalance_dates(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[datetime]:
        """
        Generate rebalance dates based on frequency.

        Args:
            start_date: Backtest start date
            end_date: Backtest end date

        Returns:
            List of rebalance dates
        """
        dates = []
        current = start_date

        if self.rebalance_frequency == 'daily':
            delta = timedelta(days=1)
        elif self.rebalance_frequency == 'weekly':
            delta = timedelta(weeks=1)
        elif self.rebalance_frequency == 'monthly':
            delta = timedelta(days=30)
        else:
            delta = timedelta(weeks=1)

        while current <= end_date:
            dates.append(current)
            current += delta

        return dates

    def _fetch_historical_data(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetch historical price data.

        Args:
            tickers: List of ticker symbols
            start_date: Start date string
            end_date: End date string

        Returns:
            DataFrame with price data
        """
        if not tickers:
            return pd.DataFrame()

        # Limit tickers to avoid timeout (yfinance can struggle with too many)
        max_tickers = 200
        if len(tickers) > max_tickers:
            logger.warning(f"Limiting from {len(tickers)} to {max_tickers} tickers for backtest")
            tickers = tickers[:max_tickers]

        try:
            logger.info(f"Downloading price data for {len(tickers)} tickers...")

            data = yf.download(
                tickers,
                start=start_date,
                end=end_date,
                progress=False,
                threads=True,
                timeout=60
            )

            if data.empty:
                logger.error("yfinance returned empty data")
                return pd.DataFrame()

            # Handle single ticker case
            if len(tickers) == 1:
                if 'Adj Close' in data.columns:
                    prices = data['Adj Close'].to_frame(name=tickers[0])
                elif 'Close' in data.columns:
                    prices = data['Close'].to_frame(name=tickers[0])
                else:
                    logger.error("No price column found in data")
                    return pd.DataFrame()
            else:
                if 'Adj Close' in data.columns:
                    prices = data['Adj Close']
                elif 'Close' in data.columns:
                    prices = data['Close']
                else:
                    logger.error("No price column found in data")
                    return pd.DataFrame()

            # Remove tickers with all NaN values
            valid_cols = prices.columns[prices.notna().any()]
            prices = prices[valid_cols]

            logger.info(f"Successfully fetched {len(prices.columns)} tickers with {len(prices)} days of data")

            return prices

        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return pd.DataFrame()

    def _calculate_hqm_scores(
        self,
        prices: pd.DataFrame,
        date_idx: int,
        min_data_days: int = 63
    ) -> pd.DataFrame:
        """
        Calculate HQM scores at a specific point in time.

        Args:
            prices: Historical price data
            date_idx: Index of current date in prices
            min_data_days: Minimum days of data required (default 63 for 3-month returns)

        Returns:
            DataFrame with HQM scores
        """
        if date_idx < min_data_days:
            logger.debug(f"Skipping date_idx {date_idx}: need at least {min_data_days} days")
            return pd.DataFrame()

        results = []
        skipped_nan = 0
        skipped_length = 0

        for ticker in prices.columns:
            try:
                ticker_prices = prices[ticker].iloc[:date_idx + 1].dropna()

                if len(ticker_prices) < min_data_days:
                    skipped_length += 1
                    continue

                current_price = ticker_prices.iloc[-1]

                if pd.isna(current_price) or current_price <= 0:
                    skipped_nan += 1
                    continue

                # Calculate returns for available periods
                return_1m = (current_price / ticker_prices.iloc[-21] - 1) if len(ticker_prices) >= 21 else None
                return_3m = (current_price / ticker_prices.iloc[-63] - 1) if len(ticker_prices) >= 63 else None
                return_6m = (current_price / ticker_prices.iloc[-126] - 1) if len(ticker_prices) >= 126 else None
                return_1y = (current_price / ticker_prices.iloc[-252] - 1) if len(ticker_prices) >= 252 else None

                # Need at least 3-month return to be useful
                if return_3m is None:
                    continue

                results.append({
                    'Ticker': ticker,
                    'Price': current_price,
                    'Return_1M': return_1m if return_1m is not None else 0,
                    'Return_3M': return_3m,
                    'Return_6M': return_6m if return_6m is not None else return_3m,
                    'Return_1Y': return_1y if return_1y is not None else return_6m if return_6m is not None else return_3m
                })

            except Exception as e:
                logger.debug(f"Error processing {ticker}: {e}")
                continue

        logger.debug(f"HQM calc: {len(results)} valid, {skipped_nan} NaN, {skipped_length} insufficient data")

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        # Calculate percentile scores
        from scipy.stats import percentileofscore

        for period in ['1M', '3M', '6M', '1Y']:
            col = f'Return_{period}'
            pct_col = f'Pct_{period}'
            valid_returns = df[col].dropna()
            if len(valid_returns) > 0:
                df[pct_col] = df[col].apply(
                    lambda x: percentileofscore(valid_returns, x, kind='mean')
                    if pd.notna(x) else 50
                )
            else:
                df[pct_col] = 50

        # Calculate HQM Score
        pct_cols = ['Pct_1M', 'Pct_3M', 'Pct_6M', 'Pct_1Y']
        df['HQM_Score'] = df[pct_cols].mean(axis=1)
        df['Min_Pct'] = df[pct_cols].min(axis=1)

        # Filter quality momentum (relaxed threshold for backtesting)
        df = df[df['Min_Pct'] >= 20]

        # Sort by HQM Score
        df = df.sort_values('HQM_Score', ascending=False)

        logger.debug(f"After filter: {len(df)} stocks qualify")

        return df.head(self.num_positions * 2)  # Get extra candidates

    def _execute_rebalance(
        self,
        date: datetime,
        target_positions: Dict[str, float],
        prices: pd.DataFrame,
        date_idx: int
    ) -> None:
        """
        Execute portfolio rebalance.

        Args:
            date: Rebalance date
            target_positions: Target positions {ticker: weight}
            prices: Price data
            date_idx: Current date index
        """
        current_prices = prices.iloc[date_idx]

        # Close positions not in target
        for ticker in list(self.positions.keys()):
            if ticker not in target_positions:
                if ticker in current_prices.index:
                    exit_price = current_prices[ticker] * (1 - self.slippage_pct)
                    position = self.positions[ticker]
                    proceeds = position['shares'] * exit_price - self.commission

                    self.trades.append({
                        'date': date,
                        'ticker': ticker,
                        'action': 'SELL',
                        'shares': position['shares'],
                        'price': exit_price,
                        'value': proceeds
                    })

                    self.cash += proceeds
                    del self.positions[ticker]

        # Calculate portfolio value
        portfolio_value = self.cash
        for ticker, pos in self.positions.items():
            if ticker in current_prices.index:
                portfolio_value += pos['shares'] * current_prices[ticker]

        # Open/adjust positions
        for ticker, weight in target_positions.items():
            if ticker not in current_prices.index:
                continue

            target_value = portfolio_value * weight
            current_price = current_prices[ticker] * (1 + self.slippage_pct)

            if ticker in self.positions:
                # Adjust existing position
                current_value = self.positions[ticker]['shares'] * current_prices[ticker]
                diff_value = target_value - current_value

                if abs(diff_value) > 100:  # Only adjust if difference > $100
                    shares_diff = int(diff_value / current_price)
                    if shares_diff > 0 and self.cash >= shares_diff * current_price:
                        # Buy more
                        cost = shares_diff * current_price + self.commission
                        self.cash -= cost
                        self.positions[ticker]['shares'] += shares_diff

                        self.trades.append({
                            'date': date,
                            'ticker': ticker,
                            'action': 'BUY',
                            'shares': shares_diff,
                            'price': current_price,
                            'value': cost
                        })
            else:
                # Open new position
                shares = int(target_value / current_price)
                if shares > 0 and self.cash >= shares * current_price:
                    cost = shares * current_price + self.commission
                    self.cash -= cost

                    self.positions[ticker] = {
                        'shares': shares,
                        'entry_price': current_price,
                        'entry_date': date
                    }

                    self.trades.append({
                        'date': date,
                        'ticker': ticker,
                        'action': 'BUY',
                        'shares': shares,
                        'price': current_price,
                        'value': cost
                    })

    def _record_portfolio_value(
        self,
        date: datetime,
        prices: pd.DataFrame,
        date_idx: int
    ) -> float:
        """
        Record portfolio value for a given date.

        Args:
            date: Current date
            prices: Price data
            date_idx: Current date index

        Returns:
            Total portfolio value
        """
        current_prices = prices.iloc[date_idx]

        invested_value = 0
        for ticker, pos in self.positions.items():
            if ticker in current_prices.index:
                invested_value += pos['shares'] * current_prices[ticker]

        total_value = self.cash + invested_value

        self.portfolio_history.append({
            'date': date,
            'total_value': total_value,
            'cash': self.cash,
            'invested': invested_value,
            'positions': len(self.positions)
        })

        return total_value

    def run(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Run the backtest.

        Args:
            tickers: Universe of tickers to trade
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            progress_callback: Optional progress callback

        Returns:
            Dict with backtest results
        """
        logger.info(f"Starting backtest from {start_date} to {end_date}")
        logger.info(f"Universe: {len(tickers)} tickers, {self.num_positions} positions")

        # Reset state
        self.trades = []
        self.portfolio_history = []
        self.positions = {}
        self.cash = self.initial_capital

        def update_progress(pct: int, msg: str) -> None:
            if progress_callback:
                progress_callback(pct, msg)
            logger.debug(f"Backtest progress: {pct}% - {msg}")

        update_progress(5, "Fetching historical data...")

        # Fetch price data
        # Add buffer for lookback calculations (1 year + margin)
        buffer_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=400)).strftime('%Y-%m-%d')

        logger.info(f"Fetching price data from {buffer_start} to {end_date} for {len(tickers)} tickers")
        prices = self._fetch_historical_data(tickers, buffer_start, end_date)

        if prices.empty:
            logger.error("Failed to fetch any historical data from yfinance")
            return {'success': False, 'error': 'Failed to fetch historical data. Check internet connection and try again.'}

        # Log data quality info
        valid_tickers = [t for t in prices.columns if prices[t].notna().sum() > 63]
        logger.info(f"Fetched data for {len(prices.columns)} tickers, {len(valid_tickers)} have sufficient data")

        if len(valid_tickers) < self.num_positions:
            logger.warning(f"Only {len(valid_tickers)} tickers have enough data for {self.num_positions} positions")

        update_progress(20, "Generating rebalance schedule...")

        # Get rebalance dates
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        rebalance_dates = self._get_rebalance_dates(start_dt, end_dt)

        update_progress(25, "Running simulation...")

        # Run simulation
        total_rebalances = len(rebalance_dates)

        rebalances_with_trades = 0
        rebalances_skipped = 0

        for i, rebalance_date in enumerate(rebalance_dates):
            # Find closest date in price data
            date_mask = prices.index <= rebalance_date
            if not date_mask.any():
                rebalances_skipped += 1
                continue

            date_idx = date_mask.sum() - 1

            # Need at least 63 days (3 months) of data for meaningful HQM calculation
            if date_idx < 63:
                rebalances_skipped += 1
                continue

            # Calculate HQM scores
            hqm_df = self._calculate_hqm_scores(prices, date_idx)

            if not hqm_df.empty:
                # Select top positions
                top_stocks = hqm_df.head(self.num_positions)
                equal_weight = 1.0 / len(top_stocks)
                target_positions = {row['Ticker']: equal_weight for _, row in top_stocks.iterrows()}

                # Execute rebalance
                self._execute_rebalance(rebalance_date, target_positions, prices, date_idx)
                rebalances_with_trades += 1
            else:
                logger.debug(f"No stocks qualified for {rebalance_date}")

            # Record portfolio value
            self._record_portfolio_value(rebalance_date, prices, date_idx)

            progress_pct = 25 + int(70 * (i + 1) / total_rebalances)
            update_progress(progress_pct, f"Processing {rebalance_date.strftime('%Y-%m-%d')}...")

        logger.info(f"Backtest complete: {rebalances_with_trades} rebalances executed, {rebalances_skipped} skipped")

        update_progress(95, "Calculating metrics...")

        # Calculate final metrics
        results = self._calculate_results()

        update_progress(100, "Backtest complete!")

        return results

    def _calculate_results(self) -> Dict[str, Any]:
        """
        Calculate backtest results and metrics.

        Returns:
            Dict with comprehensive results
        """
        if not self.portfolio_history:
            return {'success': False, 'error': 'No portfolio history generated. Try a longer date range or check if market data is available.'}

        if len(self.trades) == 0:
            logger.warning("Backtest completed but no trades were executed")

        # Convert to DataFrame
        history_df = pd.DataFrame(self.portfolio_history)
        history_df['date'] = pd.to_datetime(history_df['date'])
        history_df.set_index('date', inplace=True)

        # Calculate returns
        history_df['daily_return'] = history_df['total_value'].pct_change()
        history_df['cumulative_return'] = (history_df['total_value'] / self.initial_capital - 1) * 100

        # Calculate metrics
        final_value = history_df['total_value'].iloc[-1]
        total_return = (final_value / self.initial_capital - 1) * 100

        # Sharpe ratio (annualized)
        daily_returns = history_df['daily_return'].dropna()
        sharpe = calculate_sharpe_ratio(daily_returns)

        # Max drawdown
        max_dd, peak_date, trough_date = calculate_max_drawdown(history_df['total_value'])

        # Trade statistics
        num_trades = len(self.trades)
        if self.trades:
            trades_df = pd.DataFrame(self.trades)
            buy_trades = trades_df[trades_df['action'] == 'BUY']
            sell_trades = trades_df[trades_df['action'] == 'SELL']
        else:
            buy_trades = pd.DataFrame()
            sell_trades = pd.DataFrame()

        # Win rate (simplified - based on final position values)
        winning_trades = sum(1 for t in self.trades if t['action'] == 'SELL' and t.get('profit', 0) > 0)
        total_closed = len([t for t in self.trades if t['action'] == 'SELL'])
        win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0

        # Save to database
        self._save_results_to_db(total_return, sharpe, max_dd, num_trades, win_rate)

        return {
            'success': True,
            'initial_capital': self.initial_capital,
            'final_value': round(final_value, 2),
            'total_return': round(total_return, 2),
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'max_drawdown_peak': peak_date,
            'max_drawdown_trough': trough_date,
            'num_trades': num_trades,
            'win_rate': round(win_rate, 1),
            'num_buy_trades': len(buy_trades),
            'num_sell_trades': len(sell_trades),
            'total_commission': round(num_trades * self.commission, 2),
            'portfolio_history': history_df.reset_index().to_dict('records'),
            'trades': self.trades,
            'parameters': {
                'initial_capital': self.initial_capital,
                'num_positions': self.num_positions,
                'rebalance_frequency': self.rebalance_frequency,
                'slippage_pct': self.slippage_pct * 100,
                'commission': self.commission
            }
        }

    def _save_results_to_db(
        self,
        total_return: float,
        sharpe: float,
        max_dd: float,
        num_trades: int,
        win_rate: float
    ) -> None:
        """Save backtest results to database."""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            start_date = self.portfolio_history[0]['date'].strftime('%Y-%m-%d') if self.portfolio_history else ''
            end_date = self.portfolio_history[-1]['date'].strftime('%Y-%m-%d') if self.portfolio_history else ''
            final_value = self.portfolio_history[-1]['total_value'] if self.portfolio_history else self.initial_capital

            params = json.dumps({
                'num_positions': self.num_positions,
                'rebalance_frequency': self.rebalance_frequency,
                'slippage_pct': self.slippage_pct * 100,
                'commission': self.commission
            })

            cursor.execute('''
                INSERT INTO backtest_results
                (start_date, end_date, initial_capital, final_value, total_return,
                 sharpe_ratio, max_drawdown, win_rate, num_trades, parameters)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (start_date, end_date, self.initial_capital, final_value, total_return,
                  sharpe, max_dd, win_rate, num_trades, params))

            conn.commit()
            conn.close()
            logger.info("Backtest results saved to database")

        except Exception as e:
            logger.error(f"Failed to save backtest results: {e}")


def run_backtest(
    tickers: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: Optional[float] = None,
    num_positions: Optional[int] = None,
    rebalance_frequency: Optional[str] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """
    Convenience function to run a backtest.

    Args:
        tickers: Universe of tickers (uses database stocks if None)
        start_date: Start date (defaults to 1 year ago)
        end_date: End date (defaults to today)
        initial_capital: Starting capital
        num_positions: Number of positions
        rebalance_frequency: Rebalance frequency
        progress_callback: Progress callback function

    Returns:
        Backtest results
    """
    # Use config defaults
    if initial_capital is None:
        initial_capital = config.backtest.initial_capital
    if num_positions is None:
        num_positions = config.portfolio.default_positions
    if rebalance_frequency is None:
        rebalance_frequency = config.backtest.rebalance_frequency

    # Default dates
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start_dt = datetime.now() - timedelta(days=config.backtest.default_period_days)
        start_date = start_dt.strftime('%Y-%m-%d')

    # Get tickers from database if not provided
    if tickers is None:
        conn = get_connection()
        df = pd.read_sql_query('SELECT DISTINCT ticker FROM stocks', conn)
        conn.close()
        tickers = df['ticker'].tolist()

    if not tickers:
        return {'success': False, 'error': 'No tickers available for backtest'}

    # Create and run engine
    engine = BacktestEngine(
        initial_capital=initial_capital,
        num_positions=num_positions,
        rebalance_frequency=rebalance_frequency,
        slippage_pct=config.backtest.slippage_percent,
        commission=config.backtest.commission_per_trade
    )

    return engine.run(tickers, start_date, end_date, progress_callback)


def get_backtest_history(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent backtest results.

    Args:
        limit: Maximum number of results

    Returns:
        List of backtest results
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, run_date, start_date, end_date, initial_capital, final_value,
               total_return, sharpe_ratio, max_drawdown, win_rate, num_trades, parameters
        FROM backtest_results
        ORDER BY run_date DESC
        LIMIT ?
    ''', (limit,))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return results
