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
import time as time_lib
from functions import *
from config import *
import pandas as pd

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
                time_lib.sleep(retry_delay)
                # Try to refresh tokens
                try:
                    client.tokens.update_tokens()
                except Exception as e:
                    logger.error(f"Token refresh failed: {str(e)}")
            else:
                logger.error(f"API error for {ticker}: {response.status_code} - {response.text}")
                if attempt < max_retries - 1:
                    time_lib.sleep(retry_delay)
                else:
                    return None
                
        except Exception as e:
            logger.error(f"Exception getting price history for {ticker} (attempt {attempt + 1}): {str(e)}")
            if attempt < max_retries - 1:
                time_lib.sleep(retry_delay)
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

def place_real_order(client: Client, symbol: str, quantity: int, instruction: str, order_type: str = 'LIMIT', price: float = None) -> Dict:
    """
    Place an order - returns the order status (see check_order_status for details)
    
    Args:
        client: Schwab API client
        symbol: Stock symbol
        quantity: Number of shares
        instruction: 'SELL_SHORT' or 'BUY_TO_COVER' or 'BUY' or 'SELL'
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
                    "instruction": instruction,
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
        logger.info(f"Order ID: {order_id}")
        logger.info(f"Order status: {order_status}")    
        return order_status
            
    except Exception as e:
        logger.error(f"❌ Error placing order for {symbol}: {str(e)}")
        return {'status': 'ERROR'}

def place_bracket_order(client: Client, symbol: str, quantity: int, instruction: str, 
                       order_type: str = 'LIMIT', price: float = None, 
                       stop_price: float = None, target_price: float = None) -> Dict:
    """
    Place an order with bracket stop and target orders
    
    Args:
        client: Authenticated Schwab client
        symbol: Stock symbol
        quantity: Number of shares
        instruction: Order instruction (e.g., 'SELL_SHORT', 'BUY')
        order_type: Type of order ('LIMIT' or 'MARKET')
        price: Limit price for the entry order
        stop_price: Stop loss price
        target_price: Target profit price
    
    Returns:
        str
    """
    try:
        logger.info(f"Starting bracket order placement for {symbol}")
        logger.info(f"Parameters: quantity={quantity}, instruction={instruction}, "
                   f"order_type={order_type}, price={price}, stop={stop_price}, "
                   f"target={target_price}")
        
        # Get account hash
        linked_accounts_response = client.account_linked()
        if linked_accounts_response.status_code != 200:
            logger.error(f"Failed to get account hash. Status: {linked_accounts_response.status_code}")
            logger.error(f"Response: {linked_accounts_response.text}")
            return 'ERROR_WITH_API_CALL'
            
        account_hash = linked_accounts_response.json()[0].get('hashValue')
        logger.info(f"Got account hash: {account_hash[:8]}...")
        
        # Determine exit instruction
        if instruction == 'SELL_SHORT':
            exit_instruction = 'BUY_TO_COVER'
        elif instruction == 'BUY':
            exit_instruction = 'SELL'
        else:
            logger.error(f"Invalid instruction: {instruction}")
            return 'UNKNOWN_EXIT_INSTRUCTION'

        # Create the order
        order = {
            "orderType": order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "specialInstruction": "ALL_OR_NONE",
            "orderStrategyType": "TRIGGER",
            "orderLegCollection": [
                {
                    "instruction": instruction,
                    "quantity": int(quantity),
                    "instrument": {
                        "symbol": symbol.upper(),
                        "assetType": "EQUITY"
                    }
                }
            ],
            "childOrderStrategies": [
                {
                    "orderStrategyType": "OCO",  # One-Cancels-Other for stop and target
                    "childOrderStrategies": [
                        {
                            # Stop Loss Order
                            "orderType": "STOP",
                            "session": "NORMAL",
                            "duration": "DAY",
                            "stopPrice": stop_price,
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": [
                                {
                                    "instruction": exit_instruction,
                                    "quantity": int(quantity),
                                    "instrument": {
                                        "symbol": symbol.upper(),
                                        "assetType": "EQUITY"
                                    }
                                }
                            ]
                        },
                        {
                            # Take Profit Order
                            "orderType": "LIMIT",
                            "session": "NORMAL",
                            "duration": "DAY",
                            "price": target_price,
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": [
                                {
                                    "instruction": exit_instruction,
                                    "quantity": int(quantity),
                                    "instrument": {
                                        "symbol": symbol.upper(),
                                        "assetType": "EQUITY"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        # Add price for limit orders
        if order_type == 'LIMIT':
            order["price"] = str(price)
            logger.info(f"Added limit price: {price}")
        
        logger.info("Placing order with structure:")
        # logger.info(json.dumps(order, indent=2))
        
        # Place the order
        order_response = client.order_place(account_hash, order)
        logger.info(f"Order placement response status: {order_response.status_code}")
        
        # Log the full response for debugging
        try:
            response_json = order_response.json()
            logger.error(f"Full API Response: {json.dumps(response_json, indent=2)}")
        except:
            logger.error(f"Raw Response Text: {order_response.text}")
        
        if order_response.status_code != 201:  # 201 is success for order creation
            logger.error(f"Order placement failed. Response: {order_response.text}")
            return 'ERROR_WITH_API_CALL'
        
        # Extract order ID and check status
        order_url = order_response.headers.get('Location', '')
        order_id = order_url.split('/')[-1]
        logger.info(f"Order ID: {order_id}")
        
        order_status = check_order_status(client, account_hash, order_id)
        logger.info(f"Initial order status: {order_status}")    
        return order_status
            
    except Exception as e:
        logger.error(f"❌ Error placing order for {symbol}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return 'ERROR_WITH_API_CALL'
    
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
    

def close_matched_positions(client: Client, df: pd.DataFrame) -> None:
    """
    Close short positions that match symbols in the premarket screener results.
    
    Args:
        client: Authenticated Schwab client
        df: DataFrame containing at least 'Ticker' and 'Shares' columns
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Checking end of day positions to close...")
    
    for idx, row in df.iterrows():
        try:
            symbol = row['Ticker']
            shares = round(float(row['Shares']))  # Round to nearest integer
            
            # Check if we have a matching short position
            if check_position_match(client, symbol, shares, short=True):
                
                # Place buy to cover order
                order_result = place_real_order(
                    client=client,
                    symbol=symbol,
                    quantity=shares,
                    instruction='BUY_TO_COVER',
                    order_type='MARKET'
                )
                
                if order_result != 'ERROR_WITH_API_CALL' and order_result != 'REJECTED':
                    logger.info(f"✅ Order placed successfully for {symbol}. Status: {order_result}")
                else:
                    logger.error(f"❌ Failed to close position for {symbol}. Status: {order_result}")
            else:
                logger.info(f"No matching position found for {symbol}")
                
            # time.sleep(0.1)  # Rate limiting
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {str(e)}")
            logger.error(traceback.format_exc())
            continue

#SCHWAB API DOCUMENTATION FOR ORDERS
# https://developer.schwab.com/docs/services/5b3323445b3323445b332344/operations/5b3323445b3323445b332345

"""
{
  "session": "NORMAL",
  "duration": "DAY",
  "orderType": "MARKET",
  "cancelTime": "2024-11-22T19:43:02.866Z",
  "complexOrderStrategyType": "NONE",
  "quantity": 0,
  "filledQuantity": 0,
  "remainingQuantity": 0,
  "destinationLinkName": "string",
  "releaseTime": "2024-11-22T19:43:02.866Z",
  "stopPrice": 0,
  "stopPriceLinkBasis": "MANUAL",
  "stopPriceLinkType": "VALUE",
  "stopPriceOffset": 0,
  "stopType": "STANDARD",
  "priceLinkBasis": "MANUAL",
  "priceLinkType": "VALUE",
  "price": 0,
  "taxLotMethod": "FIFO",
  "orderLegCollection": [
    {
      "orderLegType": "EQUITY",
      "legId": 0,
      "instrument": {
        "cusip": "string",
        "symbol": "string",
        "description": "string",
        "instrumentId": 0,
        "netChange": 0,
        "type": "SWEEP_VEHICLE"
      },
      "instruction": "BUY",
      "positionEffect": "OPENING",
      "quantity": 0,
      "quantityType": "ALL_SHARES",
      "divCapGains": "REINVEST",
      "toSymbol": "string"
    }
  ],
  "activationPrice": 0,
  "specialInstruction": "ALL_OR_NONE",
  "orderStrategyType": "SINGLE",
  "orderId": 0,
  "cancelable": false,
  "editable": false,
  "status": "AWAITING_PARENT_ORDER",
  "enteredTime": "2024-11-22T19:43:02.866Z",
  "closeTime": "2024-11-22T19:43:02.866Z",
  "accountNumber": 0,
  "orderActivityCollection": [
    {
      "activityType": "EXECUTION",
      "executionType": "FILL",
      "quantity": 0,
      "orderRemainingQuantity": 0,
      "executionLegs": [
        {
          "legId": 0,
          "price": 0,
          "quantity": 0,
          "mismarkedQuantity": 0,
          "instrumentId": 0,
          "time": "2024-11-22T19:43:02.866Z"
        }
      ]
    }
  ],
  "replacingOrderCollection": [
    "string"
  ],
  "childOrderStrategies": [
    "string"
  ],
  "statusDescription": "string"
}


Order{
session	sessionstring
Enum:
[ NORMAL, AM, PM, SEAMLESS ]
duration	durationstring
Enum:
[ DAY, GOOD_TILL_CANCEL, FILL_OR_KILL, IMMEDIATE_OR_CANCEL, END_OF_WEEK, END_OF_MONTH, NEXT_END_OF_MONTH, UNKNOWN ]
orderType	orderTypestring
Enum:
[ MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP, CABINET, NON_MARKETABLE, MARKET_ON_CLOSE, EXERCISE, TRAILING_STOP_LIMIT, NET_DEBIT, NET_CREDIT, NET_ZERO, LIMIT_ON_CLOSE, UNKNOWN ]
cancelTime	string($date-time)
complexOrderStrategyType	complexOrderStrategyTypestring
Enum:
[ NONE, COVERED, VERTICAL, BACK_RATIO, CALENDAR, DIAGONAL, STRADDLE, STRANGLE, COLLAR_SYNTHETIC, BUTTERFLY, CONDOR, IRON_CONDOR, VERTICAL_ROLL, COLLAR_WITH_STOCK, DOUBLE_DIAGONAL, UNBALANCED_BUTTERFLY, UNBALANCED_CONDOR, UNBALANCED_IRON_CONDOR, UNBALANCED_VERTICAL_ROLL, MUTUAL_FUND_SWAP, CUSTOM ]
quantity	number($double)
filledQuantity	number($double)
remainingQuantity	number($double)
requestedDestination	requestedDestinationstring
Enum:
[ INET, ECN_ARCA, CBOE, AMEX, PHLX, ISE, BOX, NYSE, NASDAQ, BATS, C2, AUTO ]
destinationLinkName	string
releaseTime	string($date-time)
stopPrice	number($double)
stopPriceLinkBasis	stopPriceLinkBasisstring
Enum:
[ MANUAL, BASE, TRIGGER, LAST, BID, ASK, ASK_BID, MARK, AVERAGE ]
stopPriceLinkType	stopPriceLinkTypestring
Enum:
[ VALUE, PERCENT, TICK ]
stopPriceOffset	number($double)
stopType	stopTypestring
Enum:
[ STANDARD, BID, ASK, LAST, MARK ]
priceLinkBasis	priceLinkBasisstring
Enum:
[ MANUAL, BASE, TRIGGER, LAST, BID, ASK, ASK_BID, MARK, AVERAGE ]
priceLinkType	priceLinkTypestring
Enum:
[ VALUE, PERCENT, TICK ]
price	number($double)
taxLotMethod	taxLotMethodstring
Enum:
[ FIFO, LIFO, HIGH_COST, LOW_COST, AVERAGE_COST, SPECIFIC_LOT, LOSS_HARVESTER ]
orderLegCollection	[
xml: OrderedMap { "name": "orderLegCollection", "wrapped": true }
OrderLegCollection{
orderLegType	string
Enum:
[ EQUITY, OPTION, INDEX, MUTUAL_FUND, CASH_EQUIVALENT, FIXED_INCOME, CURRENCY, COLLECTIVE_INVESTMENT ]
legId	integer($int64)
instrument	AccountsInstrument{
oneOf ->	
AccountCashEquivalent{
assetType*	string
Enum:
[ EQUITY, OPTION, INDEX, MUTUAL_FUND, CASH_EQUIVALENT, FIXED_INCOME, CURRENCY, COLLECTIVE_INVESTMENT ]
cusip	string
symbol	string
description	string
instrumentId	integer($int64)
netChange	number($double)
type	string
Enum:
Array [ 4 ]
}
AccountEquity{
assetType*	string
Enum:
[ EQUITY, OPTION, INDEX, MUTUAL_FUND, CASH_EQUIVALENT, FIXED_INCOME, CURRENCY, COLLECTIVE_INVESTMENT ]
cusip	string
symbol	string
description	string
instrumentId	integer($int64)
netChange	number($double)
}
AccountFixedIncome{...}
AccountMutualFund{...}
AccountOption{...}
}
instruction	instructionstring
Enum:
[ BUY, SELL, BUY_TO_COVER, SELL_SHORT, BUY_TO_OPEN, BUY_TO_CLOSE, SELL_TO_OPEN, SELL_TO_CLOSE, EXCHANGE, SELL_SHORT_EXEMPT ]
positionEffect	string
Enum:
[ OPENING, CLOSING, AUTOMATIC ]
quantity	number($double)
quantityType	string
Enum:
[ ALL_SHARES, DOLLARS, SHARES ]
divCapGains	string
Enum:
[ REINVEST, PAYOUT ]
toSymbol	string
}]
activationPrice	number($double)
specialInstruction	specialInstructionstring
Enum:
[ ALL_OR_NONE, DO_NOT_REDUCE, ALL_OR_NONE_DO_NOT_REDUCE ]
orderStrategyType	orderStrategyTypestring
Enum:
[ SINGLE, CANCEL, RECALL, PAIR, FLATTEN, TWO_DAY_SWAP, BLAST_ALL, OCO, TRIGGER ]
orderId	integer($int64)
cancelable	boolean
default: false
editable	boolean
default: false
status	statusstring
Enum:
[ AWAITING_PARENT_ORDER, AWAITING_CONDITION, AWAITING_STOP_CONDITION, AWAITING_MANUAL_REVIEW, ACCEPTED, AWAITING_UR_OUT, PENDING_ACTIVATION, QUEUED, WORKING, REJECTED, PENDING_CANCEL, CANCELED, PENDING_REPLACE, REPLACED, FILLED, EXPIRED, NEW, AWAITING_RELEASE_TIME, PENDING_ACKNOWLEDGEMENT, PENDING_RECALL, UNKNOWN ]
enteredTime	string($date-time)
closeTime	string($date-time)
tag	string
accountNumber	integer($int64)
orderActivityCollection	[
xml: OrderedMap { "name": "orderActivity", "wrapped": true }
OrderActivity{
activityType	string
Enum:
Array [ 2 ]
executionType	string
Enum:
[ FILL ]
quantity	number($double)
orderRemainingQuantity	number($double)
executionLegs	[
xml: OrderedMap { "name": "executionLegs", "wrapped": true }
ExecutionLeg{
legId	integer($int64)
price	number($double)
quantity	number($double)
mismarkedQuantity	number($double)
instrumentId	integer($int64)
time	string($date-time)
}]
}]
replacingOrderCollection	[
xml: OrderedMap { "name": "replacingOrder", "wrapped": true }
{
}]
childOrderStrategies	[
xml: OrderedMap { "name": "childOrder", "wrapped": true }
{
}]
statusDescription	string
}
"""

