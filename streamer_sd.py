"""
This file is an example of how to process streaming data.
While you can process completely in the response handler this could leave the stream with a backlog.
The preferred method is to use a shared list, shown here as "shared_list"
"""
from datetime import datetime
import schwabdev
import logging
import dotenv
import time
import json
import os
import signal
from functions import *

#load environment
dotenv.load_dotenv()

# set logging level
logging.basicConfig(level=logging.INFO)

def stream_market_data(df):
    """
    Stream real-time market data for symbols in the provided dataframe
    
    Args:
        df (pd.DataFrame): Dataframe containing symbols to stream data for
    """
    # Initialize client and streamer
    client = schwabdev.Client(os.getenv('appKey'), os.getenv('appSecret'), os.getenv('callback_url'))
    streamer = client.stream

    # Set up shared list and response handler
    shared_list = []
    def response_handler(message):
        shared_list.append(message)

    # Start stream and subscribe to symbols from dataframe
    streamer.start(response_handler)
    symbols = df['symbol'].unique().tolist() # Assuming symbol column exists
    streamer.send(streamer.level_one_equities(",".join(symbols), "0,1,2,3,4,5,6,7,8"))

    # Control flags
    running = True
    MAX_RUNTIME = 120
    message_count = 0
    start_time = datetime.now()

    def signal_handler(signum, frame):
        nonlocal running
        print("\nShutdown signal received. Cleaning up...")
        running = False
        streamer.stop()
        print("Stream stopped. Exiting...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Main processing loop
    while running and (datetime.now() - start_time).seconds < MAX_RUNTIME:
        while len(shared_list) > 0:
            oldest_response = json.loads(shared_list.pop(0))
            message_count += 1
            
            elapsed_time = (datetime.now() - start_time).seconds
            if elapsed_time > 0 and elapsed_time % 10 == 0:
                print(f"\nStatus Update:")
                print(f"Running for: {elapsed_time} seconds")
                print(f"Messages received: {message_count}")
                print(f"Average messages per second: {message_count/elapsed_time:.2f}")
            
            for rtype, services in oldest_response.items():
                if rtype == "data":
                    for service in services:
                        service_type = service.get("service", None)
                        service_timestamp = service.get("timestamp", 0)
                        contents = service.get("content", [])
                        for content in contents:
                            symbol = content.pop("key", "NO KEY")
                            fields = content
                            print(f"[{service_type} - {symbol}]({datetime.fromtimestamp(service_timestamp//1000)}): {fields}")
                elif rtype == "response":
                    print(f"Response received: {services}")
                elif rtype == "notify":
                    print(f"Heartbeat received: {services}")
                else:
                    print(f"Unknown message type: {oldest_response}")
        
        time.sleep(0.5)

    print(f"\nScript completed after {MAX_RUNTIME} seconds")
    streamer.stop()