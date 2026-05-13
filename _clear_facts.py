import sys; sys.path.insert(0, '.')
from sqlalchemy import text
from etl.config import DW_ENGINE

print('Clearing stale fact tables with broken id_date references...')
with DW_ENGINE.begin() as conn:
    conn.execute(text('ALTER TABLE [FAIT_LIGNES_VENTE] NOCHECK CONSTRAINT ALL'))
    conn.execute(text('ALTER TABLE [FAIT_REGLEMENTS] NOCHECK CONSTRAINT ALL'))
    conn.execute(text('ALTER TABLE [FAIT_ECRITURES] NOCHECK CONSTRAINT ALL'))

    conn.execute(text('DELETE FROM [FAIT_LIGNES_VENTE]'))
    print('FAIT_LIGNES_VENTE cleared')
    conn.execute(text('DELETE FROM [FAIT_REGLEMENTS]'))
    print('FAIT_REGLEMENTS cleared')
    conn.execute(text('DELETE FROM [FAIT_ECRITURES]'))
    print('FAIT_ECRITURES cleared')

    conn.execute(text('ALTER TABLE [FAIT_LIGNES_VENTE] WITH CHECK CHECK CONSTRAINT ALL'))
    conn.execute(text('ALTER TABLE [FAIT_REGLEMENTS] WITH CHECK CHECK CONSTRAINT ALL'))
    conn.execute(text('ALTER TABLE [FAIT_ECRITURES] WITH CHECK CHECK CONSTRAINT ALL'))

print('Done. Now run: python -m etl.pipeline --full')
