import sys
import os

# Add parent directory to PYTHONPATH
sys.path.append(os.path.abspath("."))

from etl.api.queries import get_articles

print("Querying get_articles(year=2025, famille='Epicerie')...")
try:
    res = get_articles(year=2025, famille="Epicerie")
    print(f"  [SUCCESS] Returned {len(res)} articles:")
    for a in res[:5]:
        print(f"    {a}")
except Exception as e:
    print(f"  [ERROR] get_articles failed: {e}")
