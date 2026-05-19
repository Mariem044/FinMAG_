with open("c:/Users/marie/Desktop/myProject/FINMAG/etl/extract.py", "r", encoding="utf-8") as f:
    for idx, line in enumerate(f, 1):
        if "banque" in line.lower() or "F_BANQUE" in line:
            print(f"{idx}: {line.strip()}")
