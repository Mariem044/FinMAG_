import urllib.request
import json

def test_filters(year, segment=None, depot=None):
    params = [f"year={year}"]
    if segment: params.append(f"segment={segment}")
    if depot: params.append(f"depot={depot}")
    url = f"http://127.0.0.1:8000/api/ventes/top-familles?" + "&".join(params)
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            print(f"URL: {url}")
            if data:
                print(f"  Top 3 families: " + ", ".join([f"{x['name']}: {x['ca']:,.0f} DT" for x in data[:3]]))
            else:
                print(f"  Empty list!")
    except Exception as e:
        print(f"Failed: {e}")

print("--- TESTING DIFFERENT COMBINATIONS ---")
test_filters(2026)
test_filters(2024)
test_filters(2026, segment="SEMI-GROS")
test_filters(2026, depot="Bizerte")
test_filters(2026, depot="Tunis Nord")
