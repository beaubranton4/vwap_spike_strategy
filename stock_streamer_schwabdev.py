import schwabdev
import dotenv
import os
from config import appKey, appSecret

dotenv.load_dotenv()

client = schwabdev.Client(
    os.getenv('appKey'),
    os.getenv('appSecret'),
    show_linked=False
)

client.update_tokens_auto()

print(client.quote('AAPL').json())

