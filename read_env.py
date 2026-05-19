with open("c:/Users/marie/Desktop/myProject/FINMAG/.env", "r", encoding="utf-8") as f:
    for line in f:
        if "DB" in line or "CONN" in line or "SQL" in line:
            print(line.strip())
