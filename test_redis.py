"""Test Redis connection to Upstash"""

import os

import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
print(f"Testing connection to: {REDIS_URL.split('@')[1]}")  # Hide token

try:
    if REDIS_URL.startswith("rediss://"):
        r = redis.from_url(REDIS_URL, ssl_cert_reqs=None)
    else:
        r = redis.from_url(REDIS_URL)

    # Test connection
    r.ping()
    print("✅ Redis connection successful!")

    # Test basic operations
    r.set("test_key", "test_value")
    value = r.get("test_key")
    print(f"✅ Read/Write test successful: {value}")

    # Clean up
    r.delete("test_key")
    print("✅ Cleanup successful")

    # Test Redis Streams
    r.xadd("test_stream", {"field1": "value1"})
    print("✅ Redis Streams write successful")

    # Read from stream
    messages = r.xrange("test_stream")
    print(f"✅ Redis Streams read successful: {len(messages)} messages")

    # Clean up stream
    r.delete("test_stream")
    print("✅ Stream cleanup successful")

except Exception as e:
    print(f"❌ Connection failed: {e}")
