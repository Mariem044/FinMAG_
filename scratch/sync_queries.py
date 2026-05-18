import shutil
import os

src = "etl/api/queries.py"
dst = "dashboard/backend/api/queries.py"

if os.path.exists(src):
    shutil.copy(src, dst)
    print(f"Copied {src} to {dst} successfully!")
else:
    print(f"Source file {src} not found.")
