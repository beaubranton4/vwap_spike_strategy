import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

appKey = os.getenv('APP_KEY')
appSecret = os.getenv('APP_SECRET')