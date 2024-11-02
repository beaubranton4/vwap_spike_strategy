import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

appKey = os.getenv('appKey')
appSecret = os.getenv('appSecret')