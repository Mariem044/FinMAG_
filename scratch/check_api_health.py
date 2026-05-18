import requests

try:
    r = requests.get("http://127.0.0.1:8000/api/health", timeout=3)
    print(f"Server is UP. Status: {r.status_code}, Response: {r.json()}")
except Exception as e:
    print(f"Server is DOWN. Error: {e}")
