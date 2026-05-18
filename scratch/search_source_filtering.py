with open("etl/api/queries.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "source" in line and ("hash" in line or "sql" in line or "query" in line):
        print(f"Line {i+1}: {line.strip()}")
