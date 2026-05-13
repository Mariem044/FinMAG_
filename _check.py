import sys; sys.path.insert(0, '.')
from sqlalchemy import text
from etl.config import DW_ENGINE

with DW_ENGINE.connect() as conn:
    print('=== DIM_DATE range ===')
    r = conn.execute(text('SELECT MIN(date_val) as mn, MAX(date_val) as mx, COUNT(*) as nb FROM DIM_DATE')).fetchone()
    print('DIM_DATE: ' + str(r.mn) + ' to ' + str(r.mx) + ' (' + str(r.nb) + ' rows)')

    print('')
    print('=== Orphan dates in FAIT_REGLEMENTS ===')
    r2 = conn.execute(text("""
        SELECT COUNT(*) as nb
        FROM FAIT_REGLEMENTS fe
        LEFT JOIN DIM_DATE d ON d.id_date = fe.id_date_paiement
        WHERE fe.id_date_paiement IS NOT NULL AND d.id_date IS NULL
    """)).fetchone()
    print('Orphan id_date_paiement: ' + str(r2.nb))

    r3 = conn.execute(text("""
        SELECT COUNT(*) as nb
        FROM FAIT_REGLEMENTS fe
        LEFT JOIN DIM_DATE d ON d.id_date = fe.id_date_echeance
        WHERE fe.id_date_echeance IS NOT NULL AND d.id_date IS NULL
    """)).fetchone()
    print('Orphan id_date_echeance: ' + str(r3.nb))

    print('')
    print('=== Orphan dates in FAIT_ECRITURES ===')
    r4 = conn.execute(text("""
        SELECT COUNT(*) as nb
        FROM FAIT_ECRITURES fe
        LEFT JOIN DIM_DATE d ON d.id_date = fe.id_date
        WHERE fe.id_date IS NOT NULL AND d.id_date IS NULL
    """)).fetchone()
    print('Orphan id_date in FAIT_ECRITURES: ' + str(r4.nb))

    print('')
    print('=== Min/Max surrogate id_date in fact tables ===')
    r5 = conn.execute(text('SELECT MIN(id_date_paiement) as mn, MAX(id_date_paiement) as mx FROM FAIT_REGLEMENTS WHERE id_date_paiement IS NOT NULL')).fetchone()
    print('FAIT_REGLEMENTS id_date_paiement range: ' + str(r5.mn) + ' to ' + str(r5.mx))

    r6 = conn.execute(text('SELECT MIN(id_date) as mn, MAX(id_date) as mx FROM FAIT_ECRITURES WHERE id_date IS NOT NULL')).fetchone()
    print('FAIT_ECRITURES id_date range: ' + str(r6.mn) + ' to ' + str(r6.mx))

    r7 = conn.execute(text('SELECT MIN(id_date) as mn, MAX(id_date) as mx FROM DIM_DATE')).fetchone()
    print('DIM_DATE id_date range: ' + str(r7.mn) + ' to ' + str(r7.mx))
