import schwabdev
import dotenv
import os
import json
import base64
import requests
from datetime import datetime, timedelta
import websocket

dotenv.load_dotenv()
appKey = os.getenv('appKey')
appSecret = os.getenv('appSecret')

def auto_authenticate():
    token_file = 'schwab_token.json'
    
    # Check if token file exists and is not expired
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            token_data = json.load(f)
        
        expires_at = datetime.fromisoformat(token_data['expires_at'])
        if expires_at > datetime.now():
            return token_data['access_token']
    
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

    # Save token data
    with open(token_file, 'w') as f:
        json.dump(token_data, f)

    return token_data['access_token']

access_token = auto_authenticate()



def on_message(ws, message):
    """Print raw message to see the data structure"""
    print(f"\nReceived at {datetime.now()}:")
    try:
        # Try to pretty print if it's JSON
        data = json.loads(message)
        print(json.dumps(data, indent=2))
    except:
        # If not JSON, print raw message
        print(message)

def on_error(ws, error):
    print(f"Error occurred: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"Connection closed: {close_status_code} - {close_msg}")

def on_open(ws):
    print("Connection opened!")
    # Basic subscription message (adjust based on Schwab's documentation)
    subscribe_msg = {
        "type": "subscribe",
        "symbols": ["AAPL"]  # Start with just Apple as a test
    }
    ws.send(json.dumps(subscribe_msg))
    print("Subscription message sent")

def test_connection():
    websocket.enableTrace(True)  # Enable debug traces
    
    # Replace with the correct Schwab WebSocket URL
    ws_url = f"wss://api.schwabapi.com/v1/stream/quotes?access_token={access_token}"
    
    print(f"Attempting to connect to: {ws_url}")
    
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    ws.run_forever()

if __name__ == "__main__":
    print("Starting WebSocket test...")
    test_connection()