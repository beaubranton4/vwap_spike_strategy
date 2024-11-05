import schwabdev
import dotenv
import os
from functions import auto_authenticate
from functions import get_cash_balance, get_account_balance



if __name__ == "__main__":
    print("Fetching account balance...")
    get_account_balance() 
    print("Fetching cash balance...")
