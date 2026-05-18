import urllib.request
import json

print("Testing Filters API...")

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/dashboard/filters") as response:
        filters = json.loads(response.read().decode())
        print("\n--- Dynamic Filters ---")
        print(f"Depots (Count: {len(filters['depots'])}): {filters['depots'][:5]}")
        print(f"Segments (Count: {len(filters['segments'])}): {filters['segments']}")
        print(f"Families (Count: {len(filters['familles'])}): {filters['familles'][:5]}")
        print(f"Years: {filters['years']}")
        print(f"Modes (Count: {len(filters['modes_paiement'])}): {filters['modes_paiement']}")
except Exception as e:
    print(f"Failed to fetch dynamic filters: {e}")
