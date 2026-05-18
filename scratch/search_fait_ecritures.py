with open("etl/api/queries.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "FAIT_ECRITURES" in line:
        print(f"Line {i+1}: {line.strip()}")
