import schwabdev
import dotenv
import os
import json

# Load environment variables
dotenv.load_dotenv()

def get_account_balances():
    try:
        # Initialize client
        client = schwabdev.Client(os.getenv('appKey'), os.getenv('appSecret'), os.getenv('callback_url'))
        
        # Save tokens to json file
        tokens = {
            'access_token': client.access_token,
            'refresh_token': client.refresh_token
        }
        with open('schwab_dev_tokens.json', 'w') as f:
            json.dump(tokens, f, indent=4)
            
        # Get accounts
        accounts = client.accounts()
        
        if accounts.status_code == 200:
            accounts_data = accounts.json()
            
            print("\nAccount Balances:")
            print("-----------------")
            
            for account in accounts_data:
                account_hash = account['account_hash']
                
                # Get balances for each account
                balance = client.account_balance(account_hash)
                
                if balance.status_code == 200:
                    balance_data = balance.json()
                    print(f"\nAccount: {account['display_name']}")
                    print(f"Total Value: ${balance_data['total_balance']:.2f}")
                    print(f"Cash Balance: ${balance_data['cash_balance']:.2f}")
                else:
                    print(f"Error getting balance for account {account['display_name']}")
        else:
            print("Error retrieving accounts")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    get_account_balances()
