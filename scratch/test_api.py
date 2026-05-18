import urllib.request
import json

print("Testing API endpoints...")

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/produits/articles") as response:
        articles = json.loads(response.read().decode())
        print("\n--- Articles ---")
        for a in articles[:5]:
            print(f"Code: {a['code']} | Name: {a['designation']} | Family: {a['famille']}")
except Exception as e:
    print(f"Failed to fetch articles: {e}")

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/tresorerie/impayes-fournisseurs") as response:
        suppliers = json.loads(response.read().decode())
        print("\n--- Impayés Fournisseurs ---")
        for s in suppliers[:5]:
            print(f"Supplier: {s['fournisseur']} | Montant: {s['montant']} | Etat: {s['etat']}")
except Exception as e:
    print(f"Failed to fetch suppliers: {e}")
