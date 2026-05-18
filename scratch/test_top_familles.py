import urllib.request
import json

def test_top_familles(year):
    url = f"http://127.0.0.1:8000/api/ventes/top-familles?year={year}"
    print(f"\n--- Testing: {url} ---")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
            data = json.loads(body)
            print(f"Status: {status}")
            print(f"Top 5 families for {year}:")
            for item in data[:5]:
                print(f"  {item['name']}: {item['ca']:,.2f} DT")
    except Exception as e:
        print(f"Failed: {e}")

test_top_familles(2024)
test_top_familles(2026)
