import sys
import os

def search_files(directory, query):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".jsx") or file.endswith(".js"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if query.lower() in content.lower():
                            print(f"Match in {path}")
                except Exception:
                    pass

search_files("dashboard/frontend/src", "Approvisionnement")
