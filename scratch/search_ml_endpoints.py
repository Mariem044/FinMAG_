with open("etl/api/queries.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

endpoints = ["api/ml/forecast-ca", "api/ml/forecast-tresorerie", "api/ml/produits-alerts", "api/ml/rfm-segments"]

for i, line in enumerate(lines):
    for ep in endpoints:
        if ep in line:
            print(f"Line {i+1}: {line.strip()}")
            # print next 10 lines
            for j in range(i, min(i+12, len(lines))):
                print(f"  {j+1}: {lines[j].strip()}")
