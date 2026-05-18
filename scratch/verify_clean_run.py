import urllib.request
import json

def test_endpoint(url):
    print(f"Testing: {url}")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"  SUCCESS! Status: {response.getcode()}")
            return data
    except Exception as e:
        print(f"  FAILED: {e}")
        return None

# Test 1: Active filters
filters = test_endpoint("http://127.0.0.1:8000/api/dashboard/filters")
if filters:
    print(f"  Available Years: {filters.get('years', [])}")

# Test 2: Top Families for 2026
top_2026 = test_endpoint("http://127.0.0.1:8000/api/ventes/top-familles?year=2026")
if top_2026:
    print(f"  Top 3 families in 2026:")
    for f in top_2026[:3]:
        print(f"    {f['name']}: {f['ca']:,.2f} DT")

# Test 3: Top Families for 2024
top_2024 = test_endpoint("http://127.0.0.1:8000/api/ventes/top-familles?year=2024")
if top_2024:
    print(f"  Top 3 families in 2024:")
    for f in top_2024[:3]:
        print(f"    {f['name']}: {f['ca']:,.2f} DT")
