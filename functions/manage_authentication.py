import os
import schwabdev
import logging
import datetime
import json
from dotenv import load_dotenv

class SchwabAuthManager:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get credentials directly from .env
        self.app_key = os.getenv('appKey')
        self.app_secret = os.getenv('appSecret')
        self.callback_url = os.getenv('callback_url')
        
        # Validate credentials
        if not all([self.app_key, self.app_secret, self.callback_url]):
            raise ValueError("Missing required credentials in .env file")
            
        # Set up logging
        self.logger = logging.getLogger("SchwabAuthManager")
        
        # Ensure auth directory exists
        os.makedirs('auth', exist_ok=True)
        
        # Initialize client as None
        self.client = None

    def _check_tokens_valid(self):
        """Check if stored tokens are valid"""
        tokens_file = "auth/schwab_dev_tokens.json"
        
        if not os.path.exists(tokens_file):
            return False
            
        try:
            with open(tokens_file, 'r') as f:
                data = json.load(f)
                
            # Check if tokens exist
            token_dict = data.get('token_dictionary', {})
            if not token_dict.get('refresh_token') or not token_dict.get('access_token'):
                return False
                
            # Check refresh token expiration
            refresh_issued = datetime.datetime.fromisoformat(data.get('refresh_token_issued'))
            refresh_delta = (datetime.datetime.now(datetime.timezone.utc) - refresh_issued).total_seconds()
            
            # Return False if refresh token is older than 6 days (giving 1 day buffer)
            return refresh_delta < (6 * 24 * 60 * 60)
            
        except Exception as e:
            self.logger.error(f"Error checking tokens: {str(e)}")
            return False

    def authenticate(self):
        """
        Authenticates with Schwab API and returns a client instance.
        Handles token management automatically.
        """
        try:
            # Check if existing tokens are valid
            tokens_valid = self._check_tokens_valid()
            
            # Only clear tokens if they're invalid
            if not tokens_valid:
                self.logger.info("Existing tokens invalid or missing. Clearing tokens...")
                if os.path.exists("auth/schwab_dev_tokens.json"):
                    os.remove("auth/schwab_dev_tokens.json")
            
            # Initialize client with auto token updates
            self.client = schwabdev.Client(
                app_key=self.app_key,
                app_secret=self.app_secret,
                callback_url=self.callback_url,
                tokens_file="auth/schwab_dev_tokens.json",
                timeout=30,
                update_tokens_auto=True
            )
            
            # Force authentication only if tokens were invalid
            if not tokens_valid:
                self.logger.info("Forcing new authentication...")
                self.client.tokens.update_tokens(force=True)
            else:
                self.logger.info("Using existing valid tokens...")
            
            return self.client

        except Exception as e:
            self.logger.error(f"Authentication failed: {str(e)}")
            raise

def get_authenticated_client():
    """
    Utility function to get an authenticated client instance.
    Use this in other scripts to get a ready-to-use client.
    """
    auth_manager = SchwabAuthManager()
    return auth_manager.authenticate()
