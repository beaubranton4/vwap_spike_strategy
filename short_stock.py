import os
from schwabdev import Client
import json

def place_short_order(symbol: str, quantity: int, limit_price: float):
    """
    Place a limit short order
    
    Args:
        symbol (str): Stock symbol (e.g., 'AMZN')
        quantity (int): Number of shares to short
        limit_price (float): Limit price for the short order
    """
    # Initialize client
    client = Client(
        os.getenv('appKey'),
        os.getenv('appSecret'),
        os.getenv('callback_url')
    )
    
    try:
        # Get account hash
        linked_accounts = client.account_linked().json()
        account_hash = linked_accounts[0].get('hashValue')  # Using first account
        
        # Define the order
        order = {
            "orderType": "LIMIT",
            "price": limit_price,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "SELL_SHORT",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        
        print("\nAttempting to place short order...")
        print(f"Symbol: {symbol}")
        print(f"Quantity: {quantity}")
        print(f"Limit Price: ${limit_price:.2f}")
        print(f"Account Hash: {account_hash}")
        print(f"Order details: {json.dumps(order, indent=2)}")
        
        # Place the order
        response = client.order_place(account_hash, order)
        
        # Check response
        if response.status_code in [200, 201]:
            print("\nOrder placed successfully!")
            print("Response:", json.dumps(response.json(), indent=2))
            
            # Get order ID from response headers if available
            order_id = response.headers.get('Location')
            if order_id:
                print(f"Order ID: {order_id}")
        else:
            print(f"\nError placing order. Status code: {response.status_code}")
            print("Error message:", response.text)
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    
    # Example usage
    symbol = 'AMZN'
    quantity = 1
    limit_price = 195.45
    
    # Confirm order details before placing
    print(f"\nOrder Summary:")
    print(f"Short {quantity} shares of {symbol} at ${limit_price:.2f}")
    # confirm = input("\nDo you want to place this order? (yes/no): ").lower()
    confirm = 'yes'
    if confirm == 'yes':
        place_short_order(symbol, quantity, limit_price)
    else:
        print("Order cancelled")