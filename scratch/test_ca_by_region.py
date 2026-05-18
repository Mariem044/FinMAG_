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

# Test: Regions for 2026
reg_2026 = test_endpoint("http://127.0.0.1:8000/api/ventes/ca-by-region?year=2026")
if reg_2026:
    print(f"  Top 3 regions in 2026:")
    for r in reg_2026[:3]:
        print(f"    {r['name']}: {r['ca']:,.2f} DT")

# Test: Regions for 2024
reg_2024 = test_endpoint("http://127.0.0.1:8000/api/ventes/ca-by-region?year=2024")
if reg_2024:
    print(f"  Top 3 regions in 2024:")
    for r in reg_2024[:3]:
        print(f"    {r['name']}: {r['ca']:,.2f} DT")
