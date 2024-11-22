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
from functools import lru_cache
import time
from functions import *
from config import *

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

def get_cash_balance(client):
    try:
        
        accounts_data = client.account_details_all().json()
        
        for account in accounts_data:     
            # Return only the Cash Balance as a number
            securities_account = account.get('securitiesAccount', {})
            initial_balances = securities_account.get('initialBalances', {})
            return initial_balances.get('cashBalance', 0)
            
    except Exception as e:
        print(f"Error fetching account information: {str(e)}")

def check_order_status(client, account_hash: str, order_id: str) -> None:
    """Check and log the status of a specific order"""
    """Will return one of the following: 
      AWAITING_PARENT_ORDER, 
      AWAITING_CONDITION, 
      AWAITING_STOP_CONDITION, 
      AWAITING_MANUAL_REVIEW, 
      ACCEPTED, 
      AWAITING_UR_OUT, 
      PENDING_ACTIVATION, 
      QUEUED, 
      WORKING, 
      REJECTED, 
      PENDING_CANCEL, 
      CANCELED, 
      PENDING_REPLACE, 
      REPLACED, 
      FILLED, 
      EXPIRED, 
      NEW, 
      AWAITING_RELEASE_TIME, 
      PENDING_ACKNOWLEDGEMENT, 
      PENDING_RECALL, 
      UNKNOWN,
      ERROR_WITH_API_CALL"""
    try:
        response = client.order_details(account_hash, order_id)
        if response.status_code == 200:
            order_details = response.json()
            order_status = order_details.get('status')
            return order_status 
        else:    
            logger.error(f"Failed to get order details. Status code: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return 'ERROR_WITH_API_CALL'
            
    except Exception as e:
        logger.error(f"Error checking order status: {str(e)}")

def place_short_order(client: Client, symbol: str, quantity: int, order_type: str = 'LIMIT', price: float = None) -> Dict:
    """
    Place a short sell order - returns the order status (see check_order_status for details)
    
    Args:
        client: Schwab API client
        symbol: Stock symbol
        quantity: Number of shares
        order_type: 'MARKET' or 'LIMIT' (default: 'LIMIT')
        price: Limit price (required for LIMIT orders, ignored for MARKET orders)
    """
    try:
        # Get account hash
        linked_accounts_response = client.account_linked()
        if linked_accounts_response.status_code != 200:
            logger.error(f"Failed to place order for {symbol}")
            return 'ERROR_WITH_API_CALL'
            
        account_hash = linked_accounts_response.json()[0].get('hashValue')
        
        # Validate order type and price
        order_type = order_type.upper()
        if order_type == 'LIMIT' and price is None:
            logger.error("Price is required for LIMIT orders")
            return 'ERROR_WITH_API_CALL'
        
        # Create the order
        order = {
            "orderType": order_type,
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
        
        # Add price for limit orders
        if order_type == 'LIMIT':
            order["price"] = str(price)
        
        # Place the order
        order_response = client.order_place(account_hash, order)
        
        # Extract order ID from the response
        order_url = order_response.headers.get('Location', '')
        order_id = order_url.split('/')[-1]  # Get the last part of the URL
        # Check order status (if order is filled immediately, it will be returned as 'FAILED')
        order_status = check_order_status(client, account_hash, order_id)
        logger.info(f"Order status: {order_status}")    
        return order_status
            
    except Exception as e:
        logger.error(f"❌ Error placing order for {symbol}: {str(e)}")
        return {'status': 'ERROR'}

def cover_short_order(client: Client, symbol: str, quantity: int, order_type: str = 'LIMIT', price: float = None) -> Dict:
    """
    Place an order to cover a short position
    
    Args:
        client: Schwab API client
        symbol: Stock symbol
        quantity: Number of shares
        order_type: 'MARKET' or 'LIMIT' (default: 'LIMIT')
        price: Limit price (required for LIMIT orders, ignored for MARKET orders)
    """
    try:
        # Get account hash
        linked_accounts_response = client.account_linked()
        if linked_accounts_response.status_code != 200:
            logger.error(f"Failed to get account information for {symbol}")
            return {'status': 'ERROR'}
            
        account_hash = linked_accounts_response.json()[0].get('hashValue')
        
        # Validate order type and price
        order_type = order_type.upper()
        if order_type == 'LIMIT' and price is None:
            logger.error("Price is required for LIMIT orders")
            return {'status': 'ERROR', 'message': 'Price required for LIMIT orders'}
        
        # Create the order
        order = {
            "orderType": order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_COVER",
                    "quantity": int(quantity),
                    "instrument": {
                        "symbol": symbol.upper(),
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        
        # Add price for limit orders
        if order_type == 'LIMIT':
            order["price"] = str(price)
        
        # Place the order
        order_response = client.order_place(account_hash, order)
        
        # Log full response details
        # logger.info(f"Order Response Status: {order_response.status_code}")
        # logger.info(f"Order Response Headers: {dict(order_response.headers)}")
        # logger.info(f"Order Response Content: {order_response.content}")
        
        if order_response.status_code in [200, 201]:
            order_id = order_response.headers.get('Location', '')
            logger.info(f"✅ Successfully placed {order_type} cover order: {quantity} {symbol}" + 
                       (f" @ ${price:.2f}" if order_type == 'LIMIT' else ""))
            return {
                'status': 'SUCCESS',
                'order_id': order_id
            }
        else:
            logger.error(f"❌ Failed to place cover order for {symbol}: {order_response.text}")
            return {'status': 'ERROR'}
            
    except Exception as e:
        logger.error(f"❌ Error placing cover order for {symbol}: {str(e)}")
        return {'status': 'ERROR'}

def check_positions(client):
    """
    Get all positions across all linked accounts
    
    Args:
        client: Schwab API client instance
    
    Returns:
        list: List of dictionaries containing all positions
    """
    try:
        all_positions = []
        total_market_value = 0
        
        # Get all linked accounts first
        print("\nGetting linked accounts...")
        accounts_response = client.account_linked()
        if accounts_response.status_code != 200:
            raise Exception(f"Failed to get linked accounts: {accounts_response.text}")
            
        # Handle different possible response structures
        accounts = accounts_response.json()
        if isinstance(accounts, dict):
            accounts_list = accounts.get('accounts', [])
        elif isinstance(accounts, list):
            accounts_list = accounts
        else:
            raise Exception(f"Unexpected accounts response format: {type(accounts)}")
            
        print(f"Found {len(accounts_list)} linked accounts")
        
        # For each account, get positions
        for account in accounts_list:
            account_hash = account.get('hashValue')
            account_number = account.get('accountNumber')
            if not account_hash or not account_number:
                print("Warning: Missing account information")
                continue
                
            print(f"\nChecking positions for account: {account_number}")
            
            # Get account details including positions
            details_response = client.account_details(account_hash, fields="positions")
            if details_response.status_code != 200:
                print(f"Warning: Failed to get details for account {account_number}")
                continue
            
            account_details = details_response.json()
            
            # Check if account has positions
            positions_data = account_details.get('securitiesAccount', {}).get('positions', [])
            if not positions_data:
                print(f"No positions found in account {account_number}")
                continue
                
            # Print all positions for this account
            print(f"\nPositions in account {account_number}:")
            print("-" * 70)
            print(f"{'Symbol':<8} | {'Position':<8} | {'Quantity':<10} | {'Market Value':<12} | {'Avg Price':<10}")
            print("-" * 70)
            
            account_market_value = 0
            
            for position in positions_data:
                try:
                    # Get instrument info
                    instrument = position.get('instrument', {})
                    symbol = instrument.get('symbol', 'N/A')
                    asset_type = instrument.get('assetType', 'N/A')
                    
                    # Get position details
                    long_qty = float(position.get('longQuantity', 0))
                    short_qty = float(position.get('shortQuantity', 0))
                    market_value = float(position.get('marketValue', 0))
                    avg_price = float(position.get('averagePrice', 0))
                    
                    # Update totals
                    account_market_value += market_value
                    total_market_value += market_value
                    
                    # Determine if position is long or short
                    quantity = long_qty if long_qty > 0 else -short_qty
                    position_type = "SHORT 🔴" if quantity < 0 else "LONG 🟢"
                    
                    position_info = {
                        'account': account_number,
                        'symbol': symbol,
                        'asset_type': asset_type,
                        'position_type': position_type,
                        'quantity': abs(quantity),
                        'market_value': market_value,
                        'avg_price': avg_price,
                        'current_day_pnl': float(position.get('currentDayProfitLoss', 0)),
                        'current_day_pnl_pct': float(position.get('currentDayProfitLossPercentage', 0))
                    }
                    
                    print(
                        f"{position_info['symbol']:<8} | "
                        f"{position_type:<8} | "
                        f"{position_info['quantity']:<10.2f} | "
                        f"${position_info['market_value']:<11.2f} | "
                        f"${position_info['avg_price']:<9.2f}"
                    )
                    
                    all_positions.append(position_info)
                except Exception as e:
                    print(f"Warning: Error processing position: {e}")
                    print(f"Position data: {position}")
                    continue
            
            print("-" * 70)
            print(f"Account Total Market Value: ${account_market_value:,.2f}")
            print("-" * 70)
        
        # Print summary
        print("\nPosition Summary:")
        print(f"Total positions: {len(all_positions)}")
        long_positions = sum(1 for p in all_positions if p['position_type'] == "LONG 🟢")
        short_positions = sum(1 for p in all_positions if p['position_type'] == "SHORT 🔴")
        print(f"Long positions: {long_positions}")
        print(f"Short positions: {short_positions}")
        print(f"Total Market Value: ${total_market_value:,.2f}")
        
        return all_positions
        
    except Exception as e:
        print(f"Error checking positions: {str(e)}")
        # Print full traceback for debugging
        import traceback
        print(traceback.format_exc())
        return []

def get_all_positions(client):
    """Cache positions for 1 second to avoid multiple API calls"""
    try:
        positions = []
        accounts_response = client.account_linked()
        if accounts_response.status_code != 200:
            return positions
            
        for account in accounts_response.json():
            details_response = client.account_details(account.get('hashValue'), fields="positions")
            if details_response.status_code == 200:
                positions.extend(details_response.json().get('securitiesAccount', {}).get('positions', []))
        return positions
    except Exception:
        return []

def check_position_match(client, target_symbol, target_quantity, short):
    """Optimized version using cached positions with detailed logging"""
    try:
        target_symbol = target_symbol.upper()
        target_quantity = float(target_quantity)
        
        logger.info(f"\nChecking position match for: {target_symbol} | quantity: {target_quantity}")

        positions = get_all_positions(client)
        
        for position in positions:
            try:
                symbol = position.get('instrument', {}).get('symbol', '').upper()
                quantity = float(position.get('shortQuantity' if short else 'longQuantity', 0))
                
                if symbol == target_symbol:
                    if quantity > 0 and abs(quantity) == target_quantity:
                        logger.info(f"\n✅ Found matching {symbol} position with quantity {quantity}")
                        return True
                    else:
                        logger.info(f"\n❌ Found {symbol} but quantity {quantity} does not match target {target_quantity}")
                
            except Exception as e:
                logger.error(f"Error processing position: {str(e)}")
                continue
                
        logger.info(f"\n❌ No matching position found for {target_symbol}")
        return False
        
    except Exception as e:
        logger.error(f"Error in check_position_match: {str(e)}")
        return False