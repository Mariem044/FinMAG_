import sys
import os

# Add parent directory to PYTHONPATH
sys.path.append(os.path.abspath("."))

from etl.api.queries import get_ca_by_month, get_ca_by_region

print("1. Querying get_ca_by_month(year=2024)...")
try:
    res_month = get_ca_by_month(year=2024)
    print(f"  [SUCCESS] Returned {len(res_month)} rows:")
    for r in res_month[:5]:
        print(f"    {r}")
except Exception as e:
    print(f"  [ERROR] get_ca_by_month failed: {e}")

print("\n2. Querying get_ca_by_region(year=2024)...")
try:
    res_region = get_ca_by_region(year=2024)
    print(f"  [SUCCESS] Returned {len(res_region)} rows:")
    for r in res_region[:5]:
        print(f"    {r}")
except Exception as e:
    print(f"  [ERROR] get_ca_by_region failed: {e}")
