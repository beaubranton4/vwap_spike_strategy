# functions/__init__.py

# Importing specific functions from the backtest_functions module
from .backtest_functions import (
    next_business_day,
    buy_sell_signal,
    calculate_sell_results,
    buy_sell
)

# Importing specific functions from the schwab_functions module
from .schwab_functions import (
    auto_authenticate,
    get_stock_price_history,
    get_account_balance,
    get_cash_balance
)

from .screener_functions import (
    run_vwap_spike_screener
)

from .execute_strategy import (
    ExecuteStrategy
)

# Define __all__ to specify what is imported with *
__all__ = [
    'next_business_day',
    'buy_sell_signal',
    'calculate_sell_results',
    'buy_sell',
    'auto_authenticate',
    'get_stock_price_history',
    'get_account_balance',
    'get_cash_balance',
    'run_vwap_spike_screener',
    'ExecuteStrategy'
]
