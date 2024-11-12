import base64
import json
import os
import requests
from datetime import datetime, timedelta
import schwabdev
import traceback
import pytz
from schwabdev import Client
from typing import Dict
import logging
import time

logger = logging.getLogger(__name__)

######################################### SCHWAB API FUNCTIONS ########################################################

def auto_authenticate(appKey, appSecret):
    try:
        # Use absolute path or correct relative path
        token_file = 'auth/tokens.json'  # Adjust this path based on your project structure
        
        # Check if token file exists and is not expired
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    token_data = json.load(f)
                
                if 'expires_at' in token_data:
                    expires_at = datetime.fromisoformat(token_data['expires_at'])
                    if expires_at > datetime.now():
                        return token_data['access_token']
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"Error reading token file: {e}")
                # Continue to get new token if there's an error reading the file
        
        # If no valid token, authenticate
        headers = {
            'Authorization': f'Basic {base64.b64encode(bytes(f"{appKey}:{appSecret}", "utf-8")).decode("utf-8")}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'grant_type': 'client_credentials',
            'scope': 'openid'
        }

        response = requests.post('https://api.schwabapi.com/v1/oauth/token', headers=headers, data=data)
        if response.status_code != 200:
            raise Exception(f"Authentication failed: {response.text}")

        token_data = response.json()
        # Convert expires_in to an integer before using it
        expires_in = int(token_data.get('expires_in', 3600))  # Default to 1 hour if not present
        token_data['expires_at'] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()

        # Ensure directory exists
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        
        # Save token data
        with open(token_file, 'w') as f:
            json.dump(token_data, f)

        return token_data['access_token']
        
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        raise

def get_stock_price_history(symbol, access_token, period_type, period, frequency_type, frequency, start_date, end_date, need_extended_hours_data, need_previous_close):
    url = 'https://api.schwabapi.com/marketdata/v1/pricehistory'
    params = {
        'symbol': symbol,
        'periodType': period_type,
        'period': period,
        'frequencyType': frequency_type,
        'frequency': frequency,
        'startDate': start_date,
        'endDate': end_date,
        'needExtendedHoursData': need_extended_hours_data,
        'needPreviousClose': need_previous_close
    }
    headers = {'Authorization': f'Bearer {access_token}'}
    
    response = requests.get(url, params=params, headers=headers)
    return response.json()

    #DOCUMENTATION FOR API CALL
    # If the periodType is
    # • day - valid values are 1, 2, 3, 4, 5, 10
    # • month - valid values are 1, 2, 3, 6
    # • year - valid values are 1, 2, 3, 5, 10, 15, 20
    # • ytd - valid values are 1

    # If the period is not specified and the periodType is
    # • day - default period is 10.
    # • month - default period is 1.
    # • year - default period is 1.
    # • ytd - default period is 1.

    # period
    # frequencyType
    # string
    # (query)
    # The time frequencyType

    # If the periodType is
    # • day - valid value is minute
    # • month - valid values are daily, weekly
    # • year - valid values are daily, weekly, monthly
    # • ytd - valid values are daily, weekly

    # If frequencyType is not specified, default value depends on the periodType
    # • day - defaulted to minute.
    # • month - defaulted to weekly.
    # • year - defaulted to monthly.
    # • ytd - defaulted to weekly.

    # Available values : minute, daily, weekly, monthly


    # --
    # frequency
    # integer($int32)
    # (query)
    # The time frequency duration

    # If the frequencyType is
    # • minute - valid values are 1, 5, 10, 15, 30
    # • daily - valid value is 1
    # • weekly - valid value is 1
    # • monthly - valid value is 1

    # If frequency is not specified, default value is 1

    # frequency
    # startDate
    # integer($int64)
    # (query)
    # The start date, Time in milliseconds since the UNIX epoch eg 1451624400000
    # If not specified startDate will be (endDate - period) excluding weekends and holidays.

    # startDate
    # endDate
    # integer($int64)
    # (query)
    # The end date, Time in milliseconds since the UNIX epoch eg 1451624400000
    # If not specified, the endDate will default to the market close of previous business day.

def get_price_history_with_schwabdev(client, ticker, period_type, period, frequency_type, frequency, 
                                    start_time, end_time, need_extended_hours_data, need_previous_close,
                                    max_retries=3, retry_delay=5):
    """
    Wrapper function for schwabdev price_history with retry logic
    Returns the same format as the original get_stock_price_history function
    """
    for attempt in range(max_retries):
        try:
            response = client.price_history(
                symbol=ticker,
                periodType=period_type,
                period=period,
                frequencyType=frequency_type,
                frequency=frequency,
                startDate=start_time,
                endDate=end_time,
                needExtendedHoursData=need_extended_hours_data,
                needPreviousClose=need_previous_close
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:  # Authentication error
                logger.warning(f"Authentication error on attempt {attempt + 1} for {ticker}, retrying...")
                time.sleep(retry_delay)
                # Try to refresh tokens
                try:
                    client.tokens.update_tokens()
                except Exception as e:
                    logger.error(f"Token refresh failed: {str(e)}")
            else:
                logger.error(f"API error for {ticker}: {response.status_code} - {response.text}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    return None
                
        except Exception as e:
            logger.error(f"Exception getting price history for {ticker} (attempt {attempt + 1}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return None
    
    return None


    ############################FUNCTIONS FOR PLACING ORDERS AND MONITORING ACCOUNT#############################

def get_account_balance(client):
    try:
        
        # Rest of the function remains the same
        response = client.account_details_all()
        if not response.ok:
            print(f"API Error: {response.status_code} - {response.text}")
            return 0
            
        accounts_data = response.json()
        if not accounts_data:
            print("No account data received")
            return 0
            
        for account in accounts_data:
            securities_account = account.get('securitiesAccount', {})
            initial_balances = securities_account.get('initialBalances', {})
            return initial_balances.get('accountValue', 0)
            
    except Exception as e:
        print(f"Error fetching account information: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return 0

def get_cash_balance():
    try:
        # Format tokens first
        formatted_tokens = format_tokens_for_client()
        
        # Initialize client with formatted tokens
        client = schwabdev.Client(
            os.getenv('appKey'),
            os.getenv('appSecret'),
            os.getenv('callback_url'),
            tokens_file="auth/schwab_dev_tokens.json",  # Use formatted tokens instead of tokens_file
            timeout=10, 
            update_tokens_auto=True
        )
        
        accounts_data = client.account_details_all().json()
        
        for account in accounts_data:     
            # Return only the Cash Balance as a number
            cash_balance = current_balances.get('cashBalance', 0)
            print(cash_balance)
            return cash_balance
            
    except Exception as e:
        print(f"Error fetching account information: {str(e)}")

def place_short_order(client: Client, symbol: str, quantity: int, price: float) -> Dict:
    """Place a short sell order"""
    try:
        # Get account hash
        linked_accounts_response = client.account_linked()
        if linked_accounts_response.status_code != 200:
            logger.error(f"Failed to get account information for {symbol}")
            return {'status': 'ERROR'}
            
        account_hash = linked_accounts_response.json()[0].get('hashValue')
        
        # Create the order
        order = {
            "orderType": "LIMIT",
            "price": str(price),
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL_SHORT",
                    "quantity": int(quantity),
                    "instrument": {
                        "symbol": symbol.upper(),
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        
        # Place the order
        order_response = client.order_place(account_hash, order)
        
        if order_response.status_code in [200, 201]:
            order_id = order_response.headers.get('Location', '')
            logger.info(f"✅ Successfully placed short order: {quantity} {symbol} @ ${price:.2f}")
            return {
                'status': 'SUCCESS',
                'order_id': order_id
            }
        else:
            logger.error(f"❌ Failed to place order for {symbol}: {order_response.text}")
            return {'status': 'ERROR'}
            
    except Exception as e:
        logger.error(f"❌ Error placing order for {symbol}: {str(e)}")
        return {'status': 'ERROR'}

