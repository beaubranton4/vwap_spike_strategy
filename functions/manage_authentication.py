from schwabdev import Client
import os
import logging

def get_authenticated_client():
    """
    Get an authenticated Schwab client using schwabdev's built-in token management
    """
    try:
        # Initialize client with auto token updates
        client = Client(
            os.getenv('appKey'),
            os.getenv('appSecret'),
            os.getenv('callback_url'),
            tokens_file="auth/schwab_dev_tokens.json",
            timeout=30,
            update_tokens_auto=True  # This enables automatic token updates
        )
        
        return client
        
    except Exception as e:
        logging.error(f"Error in client authentication: {str(e)}")
        raise
