import re

filepath = "c:/Users/marie/Desktop/myProject/FINMAG/dashboard/frontend/src/lib/api.js"
pattern = re.compile(r"rapprochement", re.IGNORECASE)

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    for idx, line in enumerate(f, 1):
        if pattern.search(line):
            print(f"{idx}: {line.strip()}")
