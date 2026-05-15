import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from etl.config import DW_ENGINE, GRT_ENGINE

def n(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()

print("GRT client reglements:", n(GRT_ENGINE, "SELECT COUNT(*) FROM F_ReglementClient"))
print("GRT fournisseur reglements:", n(GRT_ENGINE, "SELECT COUNT(*) FROM F_ReglementFournisseur"))
total_grt = n(GRT_ENGINE, "SELECT COUNT(*) FROM F_ReglementClient") + n(GRT_ENGINE, "SELECT COUNT(*) FROM F_ReglementFournisseur")
print("GRT total combined:", total_grt)
print("DW FAIT_REGLEMENTS:", n(DW_ENGINE, "SELECT COUNT(*) FROM FAIT_REGLEMENTS"))
print("DW duplicate RT_Num:", n(DW_ENGINE, """
    SELECT COUNT(*) FROM (
        SELECT RT_Num, COUNT(*) cnt FROM FAIT_REGLEMENTS
        WHERE RT_Num IS NOT NULL
        GROUP BY RT_Num HAVING COUNT(*)>1
    ) d
"""))
print("DW rows with no client AND no fournisseur:", n(DW_ENGINE,
    "SELECT COUNT(*) FROM FAIT_REGLEMENTS WHERE id_client IS NULL AND id_fournisseur IS NULL"))
