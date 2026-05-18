import urllib.request
import json

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=3) as response:
        status = response.getcode()
        body = response.read().decode("utf-8")
        print(f"API is running! Status: {status}")
        print(f"Response: {body}")
except Exception as e:
    print(f"API is down or unreachable: {e}")
