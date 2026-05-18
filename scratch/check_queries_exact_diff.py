import difflib

file1 = r"c:\Users\marie\Desktop\myProject\FINMAG\etl\api\queries.py"
file2 = r"c:\Users\marie\Desktop\myProject\FINMAG\dashboard\backend\api\queries.py"

with open(file1, "r", encoding="utf-8") as f1, open(file2, "r", encoding="utf-8") as f2:
    lines1 = f1.readlines()
    lines2 = f2.readlines()

diff = difflib.unified_diff(lines1, lines2, fromfile="etl", tofile="dashboard")
print("".join(list(diff)[:50])) # Show first 50 lines of diff
