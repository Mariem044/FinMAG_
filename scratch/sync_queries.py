import shutil
import os

src = r"c:\Users\marie\Desktop\myProject\FINMAG\dashboard\backend\api\queries.py"
dst = r"c:\Users\marie\Desktop\myProject\FINMAG\etl\api\queries.py"

# Back up the destination file first to be safe
backup = dst + ".bak"
shutil.copy2(dst, backup)
print("Backed up etl/api/queries.py to", backup)

# Overwrite destination file with source
shutil.copy2(src, dst)
print("Successfully synced queries.py from dashboard/backend/api to etl/api!")
