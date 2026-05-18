import requests

BASE_URL = "http://127.0.0.1:8000/api/tresorerie"

def test_endpoint(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint}"
    print(f"Testing GET {url} with params {params}...")
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            print(f"  [SUCCESS] Status: 200. Data: {r.json()}\n")
        else:
            print(f"  [ERROR] Status: {r.status_code}. Response: {r.text}\n")
    except Exception as e:
        print(f"  [EXCEPTION] Failed to connect: {e}\n")

# 1. Test Summary without filters
test_endpoint("summary")

# 2. Test Summary with Tunis Nord depot
test_endpoint("summary", {"depot": "Tunis Nord"})

# 3. Test Summary with specific year and segment
test_endpoint("summary", {"year": 2026, "segment": "DÉTAILLANTS"})

# 4. Test Aging
test_endpoint("aging", {"depot": "Sousse"})
