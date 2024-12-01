# functions/__init__.py

# Importing specific functions from the backtest_functions module
from .backtest_functions import (
    next_business_day,
    last_trading_day,
    buy_sell_signal,
    calculate_sell_results,
    buy_sell
)

# Importing specific functions from the schwab_functions module
from .schwab_functions import (
    auto_authenticate,
    get_stock_price_history,
    get_price_history_with_schwabdev,
    get_account_balance,
    get_cash_balance,
    place_real_order,
    place_bracket_order,
    check_positions,
    check_position_match,
    get_all_positions,
    check_order_status,
    close_matched_positions
)

# Importing authentication functions
from .manage_authentication import (
    get_authenticated_client
)

from .screener_functions import (
    run_vwap_spike_screener,
    run_premarket_screener,
    calculate_shares 
)

from .execute_strategy import (
    ExecuteStrategy
)

# Define __all__ to specify what is imported with *
__all__ = [

    # Backtest functions
    'next_business_day',
    'last_trading_day',
    'buy_sell_signal',
    'calculate_sell_results',
    'buy_sell',
    
    # Schwab API functions
    'auto_authenticate',
    'get_stock_price_history',
    'get_price_history_with_schwabdev',
    'get_account_balance',
    'get_cash_balance',
    'place_real_order',
    'place_bracket_order',
    'check_positions',
    'check_position_match',
    'get_all_positions',
    'check_order_status',
    'close_matched_positions',
    
    # Authentication functions
    'get_authenticated_client',   
    
    # Screener functions
    'run_vwap_spike_screener',   
    'run_premarket_screener',
    'calculate_shares',
    
    # Strategy execution
    'ExecuteStrategy'
]
