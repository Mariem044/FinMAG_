import urllib.request
import json
import urllib.parse

def test_depot(depot_name):
    encoded_depot = urllib.parse.quote(depot_name)
    url = f"http://127.0.0.1:8000/api/ventes/top-familles?year=2026&depot={encoded_depot}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            print(f"Depot: {depot_name}")
            if data:
                print(f"  Top 3: " + ", ".join([f"{x['name']}: {x['ca']:,.0f} DT" for x in data[:3]]))
            else:
                print(f"  Empty list!")
    except Exception as e:
        print(f"Failed {depot_name}: {e}")

depots = ["Bizerte", "Manouba", "Kairouan", "Sousse", "Tunis Nord", "Ariana", "Béja", "Kasserine"]
for d in depots:
    test_depot(d)
