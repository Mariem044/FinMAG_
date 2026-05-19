from sqlalchemy import text
from etl.config import DW_ENGINE

sql = """
    SELECT
        tm.MC_TypeMvt,
        tm.MC_IntituleTypeMvt,
        COALESCE(
            NULLIF(tm.MC_IntituleTypeMvt, ''),
            CASE tm.MC_TypeMvt
                WHEN 1 THEN 'Recette'
                WHEN 2 THEN 'Dépense'
                WHEN 3 THEN 'Transfert'
                ELSE CONCAT('Mouvement ', tm.MC_TypeMvt)
            END
        ) AS name,
        SUM(ABS(COALESCE(e.MC_Credit, 0)) + ABS(COALESCE(e.MC_Debit, 0))) AS value
    FROM FAIT_ECRITURES e
    LEFT JOIN DIM_TYPE_MVT_CAISSE tm ON tm.id_type_mvt = e.id_type_mvt_caisse
    WHERE e.grain = 3
    GROUP BY tm.MC_TypeMvt, tm.MC_IntituleTypeMvt
    ORDER BY value DESC
"""

with DW_ENGINE.connect() as conn:
    res = conn.execute(text(sql))
    rows = res.fetchall()
    for r in rows[:15]:
        print(dict(r._mapping))
