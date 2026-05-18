import filecmp

file1 = r"c:\Users\marie\Desktop\myProject\FINMAG\etl\api\queries.py"
file2 = r"c:\Users\marie\Desktop\myProject\FINMAG\dashboard\backend\api\queries.py"

are_equal = filecmp.cmp(file1, file2, shallow=False)
print("Are the two queries.py identical?", are_equal)

with open(file1, "r", encoding="utf-8") as f1, open(file2, "r", encoding="utf-8") as f2:
    lines1 = f1.readlines()
    lines2 = f2.readlines()
    print(f"File 1 length: {len(lines1)} lines")
    print(f"File 2 length: {len(lines2)} lines")
