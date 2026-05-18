import sys
import os

with open("etl/extract.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "def extract_dim_depot" in line:
        # print 20 lines from here
        for j in range(i, min(i+30, len(lines))):
            print(f"Line {j+1}: {lines[j].strip()}")
        break
