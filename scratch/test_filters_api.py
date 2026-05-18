import urllib.request
import json

def test_endpoint(url):
    print(f"\n--- Testing: {url} ---")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
            data = json.loads(body)
            print(f"Status: {status}")
            if "years" in data:
                print("Available Years:", data["years"])
            elif "ca_total" in data:
                print("2026 KPIs:")
                print(f"  CA Total: {data['ca_total']:,.2f} DT")
                print(f"  Nb Commandes: {data['nb_commandes']}")
                print(f"  Clients Actifs: {data['nb_clients_actifs']}")
                print(f"  Marge Brute: {data.get('marge_brute_pct', 0)}%")
                print(f"  Taux Recouvrement: {data.get('taux_recouvrement_pct', 0)}%")
            else:
                print("Data Keys:", list(data.keys()))
    except Exception as e:
        print(f"Failed: {e}")

test_endpoint("http://127.0.0.1:8000/api/dashboard/filters")
test_endpoint("http://127.0.0.1:8000/api/dashboard/kpis?year=2026")
