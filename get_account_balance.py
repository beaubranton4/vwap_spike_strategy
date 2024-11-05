import schwabdev
import dotenv
import os
import json
from datetime import datetime

# Load environment variables
dotenv.load_dotenv()

def get_account_balance():
    # Initialize client
    client = schwabdev.Client(
        os.getenv('appKey'),
        os.getenv('appSecret'),
        os.getenv('callback_url')
    )
    
    try:
        accounts_data = client.account_details_all().json()
        
        for account in accounts_data:
            securities_account = account.get('securitiesAccount', {})
            current_balances = securities_account.get('currentBalances', {})
            initial_balances = securities_account.get('initialBalances', {})
            
            print("\nAccount Information:")
            print("-" * 50)
            print(f"Account Number: {securities_account.get('accountNumber', 'N/A')}")
            print(f"Available Funds: ${current_balances.get('availableFunds', 0):,.2f}")
            print(f"Cash Balance: ${current_balances.get('cashBalance', 0):,.2f}")
            print(f"Account Value: ${initial_balances.get('accountValue', 0):,.2f}")
            print("-" * 50)
            
    except Exception as e:
        print(f"Error fetching account information: {str(e)}")

if __name__ == "__main__":
    print("Fetching account balance...")
    get_account_balance() 