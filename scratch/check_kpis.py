import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from etl.config import DW_ENGINE
from sqlalchemy import text

with DW_ENGINE.connect() as conn:
    # 1. Latest year
    res = conn.execute(text("""
        SELECT MAX(d.annee) AS annee
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        WHERE dom.DO_Domaine = 0
    """)).fetchone()
    year = res[0]
    print(f"Latest year in sales: {year}")
    
    # 2. Latest active month for that year
    meta = conn.execute(text("""
        WITH monthly_stats AS (
            SELECT AVG(CAST(row_cnt AS FLOAT)) AS avg_rows
            FROM (
                SELECT d2.annee, d2.mois, COUNT(*) AS row_cnt
                FROM FAIT_LIGNES_VENTE f2
                JOIN DIM_DOMAINE dom2 ON dom2.id_domaine = f2.id_domaine
                JOIN DIM_DATE d2 ON d2.id_date = f2.id_date
                WHERE dom2.DO_Domaine = 0
                GROUP BY d2.annee, d2.mois
            ) counts
        )
        SELECT
            MAX(CASE WHEN cnt.row_cnt >= ms.avg_rows * 0.5 THEN d.mois ELSE 0 END) AS latest_month
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        JOIN DIM_DATE d ON d.id_date = f.id_date
        CROSS JOIN monthly_stats ms
        JOIN (
            SELECT d2.annee, d2.mois, COUNT(*) AS row_cnt
            FROM FAIT_LIGNES_VENTE f2
            JOIN DIM_DOMAINE dom2 ON dom2.id_domaine = f2.id_domaine
            JOIN DIM_DATE d2 ON d2.id_date = f2.id_date
            WHERE dom2.DO_Domaine = 0
            GROUP BY d2.annee, d2.mois
        ) cnt ON cnt.annee = d.annee AND cnt.mois = d.mois
        WHERE dom.DO_Domaine = 0
        AND d.annee = :year
    """), {"year": year}).fetchone()
    latest_month = meta[0] if meta and meta[0] else 12
    print(f"Latest active month for {year}: {latest_month}")
    
    # 3. KPIs
    sql = """
        SELECT
            SUM(CASE WHEN d.annee = :latest_year THEN f.DL_MontantHT ELSE 0 END) AS ca_total,
            SUM(CASE WHEN d.annee = :latest_year - 1
                AND d.mois <= :latest_month
                THEN f.DL_MontantHT ELSE 0 END) AS ca_total_n1,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year AND f.DO_Piece_hash IS NOT NULL THEN
                CONCAT(f.DO_Piece_hash, '-', COALESCE(f.id_type_doc, 0))
            END) AS nb_commandes,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year - 1 AND d.mois <= :latest_month AND f.DO_Piece_hash IS NOT NULL THEN
                CONCAT(f.DO_Piece_hash, '-', COALESCE(f.id_type_doc, 0))
            END) AS nb_commandes_n1,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year THEN f.id_client END) AS nb_clients_actifs,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year - 1 AND d.mois <= :latest_month THEN f.id_client END) AS nb_clients_actifs_n1,
            SUM(CASE WHEN d.annee = :latest_year
                        AND f.DL_CMUP IS NOT NULL
                        AND f.DL_CMUP > 0
                        AND f.DL_Qte IS NOT NULL
                        AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP)
                THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP)
                ELSE NULL
            END) AS marge_brute,
            SUM(CASE WHEN d.annee = :latest_year
                        AND f.DL_CMUP IS NOT NULL
                        AND f.DL_CMUP > 0
                        AND f.DL_Qte IS NOT NULL
                THEN f.DL_MontantHT
                ELSE 0
            END) AS ca_avec_cout,
            COUNT(CASE WHEN d.annee = :latest_year
                            AND f.DL_CMUP IS NOT NULL
                            AND f.DL_CMUP > 0
                            AND f.DL_Qte IS NOT NULL
                            AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP) THEN 1 END) AS nb_lignes_avec_cout,
            SUM(CASE WHEN d.annee = :latest_year - 1
                        AND d.mois <= :latest_month
                        AND f.DL_CMUP IS NOT NULL
                        AND f.DL_CMUP > 0
                        AND f.DL_Qte IS NOT NULL
                        AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP)
                THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP)
                ELSE NULL
            END) AS marge_brute_n1,
            SUM(CASE WHEN d.annee = :latest_year - 1
                        AND d.mois <= :latest_month
                        AND f.DL_CMUP IS NOT NULL
                        AND f.DL_CMUP > 0
                        AND f.DL_Qte IS NOT NULL
                THEN f.DL_MontantHT
                ELSE 0
            END) AS ca_avec_cout_n1,
            COUNT(CASE WHEN d.annee = :latest_year - 1
                            AND d.mois <= :latest_month
                            AND f.DL_CMUP IS NOT NULL
                            AND f.DL_CMUP > 0
                            AND f.DL_Qte IS NOT NULL
                            AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP) THEN 1 END) AS nb_lignes_avec_cout_n1
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE dom.DO_Domaine = 0
        AND d.annee IN (:latest_year, :latest_year - 1)
    """
    row = conn.execute(text(sql), {"latest_year": year, "latest_month": latest_month}).fetchone()
    
    print("\n--- KPI RESULTS ---")
    ca_total = row.ca_total
    ca_total_n1 = row.ca_total_n1
    print(f"CA Total (N): {ca_total}")
    print(f"CA Total (N-1 up to M{latest_month}): {ca_total_n1}")
    print(f"CA Growth Pct: {((ca_total - ca_total_n1) / ca_total_n1 * 100) if ca_total_n1 else 0:.4f}%")
    
    nb_cmd = row.nb_commandes
    nb_cmd_n1 = row.nb_commandes_n1
    print(f"Nb Commandes (N): {nb_cmd}")
    print(f"Nb Commandes (N-1): {nb_cmd_n1}")
    print(f"Nb Commandes Growth Pct: {((nb_cmd - nb_cmd_n1) / nb_cmd_n1 * 100) if nb_cmd_n1 else 0:.4f}%")
    
    nb_cli = row.nb_clients_actifs
    nb_cli_n1 = row.nb_clients_actifs_n1
    print(f"Nb Clients Actifs (N): {nb_cli}")
    print(f"Nb Clients Actifs (N-1): {nb_cli_n1}")
    print(f"Nb Clients Actifs Growth Pct: {((nb_cli - nb_cli_n1) / nb_cli_n1 * 100) if nb_cli_n1 else 0:.4f}%")
    
    raw_marge = row.marge_brute
    ca_avec_cout = row.ca_avec_cout
    nb_avec_cout = row.nb_lignes_avec_cout
    marge_brute_pct = (raw_marge / ca_avec_cout * 100) if (ca_avec_cout > 0 and raw_marge is not None and nb_avec_cout > 0) else 0
    print(f"Marge Brute Pct (N): {marge_brute_pct:.4f}%")
    print(f"CA avec coût (N): {ca_avec_cout}")
    
    raw_marge_n1 = row.marge_brute_n1
    ca_avec_cout_n1 = row.ca_avec_cout_n1
    nb_avec_cout_n1 = row.nb_lignes_avec_cout_n1
    marge_brute_pct_n1 = (raw_marge_n1 / ca_avec_cout_n1 * 100) if (ca_avec_cout_n1 > 0 and raw_marge_n1 is not None and nb_avec_cout_n1 > 0) else 0
    print(f"Marge Brute Pct (N-1): {marge_brute_pct_n1:.4f}%")
    print(f"Marge Brute Growth: {marge_brute_pct - marge_brute_pct_n1:.4f}%")

    # 4. Recovery rates
    rec_sql = """
        WITH deduped AS (
            SELECT
                r.RT_Num,
                MAX(r.RT_Montant)         AS RT_Montant,
                MAX(r.DR_Regle)           AS DR_Regle,
                MAX(r.id_date_paiement)   AS id_date_paiement
            FROM FAIT_REGLEMENTS r WITH (NOLOCK)
            WHERE r.RT_Num IS NOT NULL AND r.id_client IS NOT NULL
            GROUP BY r.RT_Num
        )
        SELECT
            dt.annee,
            SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
            SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes
        FROM deduped d
        JOIN DIM_DATE dt WITH (NOLOCK) ON dt.id_date = d.id_date_paiement
        WHERE dt.annee IN (:year, :year - 1)
        GROUP BY dt.annee
    """
    rec_rows = conn.execute(text(rec_sql), {"year": year}).fetchall()
    rec_n = 0.0
    rec_n1 = 0.0
    for r in rec_rows:
        enc = r.encaissements
        imp = r.impayes
        tot = enc + imp
        rate = (enc / tot * 100) if tot else 0.0
        print(f"Year {r.annee}: encaissements={enc}, impayes={imp}, total={tot}, rate={rate:.4f}%")
        if r.annee == year:
            rec_n = rate
        elif r.annee == year - 1:
            rec_n1 = rate
    print(f"Recovery Rate Growth: {rec_n - rec_n1:.4f}%")
