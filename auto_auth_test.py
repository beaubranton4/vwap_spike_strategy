from functions import *
from config import *

access_token = auto_authenticate(appKey, appSecret)
aapl_price_history = get_stock_price_history('AAPL', access_token, period_type, period, frequency_type, frequency,  start_time, end_time,need_extended_hours_data, need_previous_close)
# Convert to DataFrame
aapl_df = pd.DataFrame(aapl_price_history['candles'])

# Rename columns to match the required format
aapl_df.rename(columns={
    'datetime': 'Datetime',
    'open': 'Open',
    'high': 'High',
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume'
}, inplace=True)

# Print the result
print(aapl_df.head()) 
print('SUCCESS IF I SEE APPLE STOCK DATA!!!')
