import urllib.request
import json

def test_kpis(year):
    url = f"http://127.0.0.1:8000/api/dashboard/kpis?year={year}"
    print(f"Testing: {url}")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"  SUCCESS!")
            print(f"  CA Total: {data.get('ca_total'):,.2f} DT")
            print(f"  Nb Commandes: {data.get('nb_commandes')}")
            print(f"  Marge Brute %: {data.get('marge_brute_pct')}%")
    except Exception as e:
        print(f"  FAILED: {e}")

test_kpis(2026)
test_kpis(2024)
