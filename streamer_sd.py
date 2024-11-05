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

#load environment
dotenv.load_dotenv()

# set logging level
logging.basicConfig(level=logging.INFO)

# make a client
client = schwabdev.Client(os.getenv('appKey'), os.getenv('appSecret'), os.getenv('callback_url'))
streamer = client.stream

#define a response handler
shared_list = []
def response_handler(message):
    shared_list.append(message)

# start the stream and send in what symbols we want.
streamer.start(response_handler)
streamer.send(streamer.level_one_equities("NVDA", "0,1,2,3,4,5,6,7,8"))

# Add a flag to control the main loop
running = True

# Define signal handler
def signal_handler(signum, frame):
    global running
    print("\nShutdown signal received. Cleaning up...")
    running = False
    streamer.stop()
    print("Stream stopped. Exiting...")

# Register the signal handler correctly
signal.signal(signal.SIGINT, signal_handler)  # Changed this line
signal.signal(signal.SIGTERM, signal_handler)  # Optional: handle SIGTERM as well

# Add a counter to track messages
message_count = 0
start_time = datetime.now()

# Add this near the start of the script
MAX_RUNTIME = 120  # Run for 60 seconds

# Modify the main loop to include status updates
# while running:
while running and (datetime.now() - start_time).seconds < MAX_RUNTIME:
    while len(shared_list) > 0:
        oldest_response = json.loads(shared_list.pop(0))
        message_count += 1
        
        # Print status every 10 seconds
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
                print(f"Response received: {services}")  # Print response messages
            elif rtype == "notify":
                print(f"Heartbeat received: {services}")  # Print heartbeat messages
            else:
                print(f"Unknown message type: {oldest_response}")
    
    time.sleep(0.5)

print(f"\nScript completed after {MAX_RUNTIME} seconds")
streamer.stop()