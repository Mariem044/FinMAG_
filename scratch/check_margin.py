import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import DW_ENGINE
from sqlalchemy import text

with DW_ENGINE.connect() as conn:
    print("--- GROSS MARGIN ANALYSIS FOR 2024 ---")
    
    # Let's count total lines with valid cost and their types
    sql = """
        SELECT
            COUNT(*) AS total_rows,
            SUM(CASE WHEN f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP) THEN 1 ELSE 0 END) AS profitable_rows,
            SUM(CASE WHEN f.DL_MontantHT = (f.DL_Qte * f.DL_CMUP) THEN 1 ELSE 0 END) AS break_even_rows,
            SUM(CASE WHEN f.DL_MontantHT < (f.DL_Qte * f.DL_CMUP) THEN 1 ELSE 0 END) AS loss_rows,
            SUM(CASE WHEN f.DL_CMUP IS NULL OR f.DL_CMUP <= 0 OR f.DL_Qte IS NULL THEN 1 ELSE 0 END) AS missing_cost_rows
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE dom.DO_Domaine = 0
        AND d.annee = 2024
    """
    row = conn.execute(text(sql)).fetchone()
    print(f"Total sales lines in 2024: {row.total_rows}")
    print(f"Profitable lines (> cost): {row.profitable_rows} ({row.profitable_rows/row.total_rows*100:.2f}%)")
    print(f"Break-even lines (= cost): {row.break_even_rows} ({row.break_even_rows/row.total_rows*100:.2f}%)")
    print(f"Loss-making lines (< cost): {row.loss_rows} ({row.loss_rows/row.total_rows*100:.2f}%)")
    print(f"Lines missing cost data: {row.missing_cost_rows} ({row.missing_cost_rows/row.total_rows*100:.2f}%)")
    
    # Calculate margins
    calc_sql = """
        SELECT
            -- Original Formula (profitable only)
            SUM(CASE WHEN f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP) THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP) END) AS original_margin,
            
            -- True Formula (including all lines with cost)
            SUM(f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP)) AS true_margin,
            
            -- Denominator
            SUM(CASE WHEN f.DL_CMUP IS NOT NULL AND f.DL_CMUP > 0 AND f.DL_Qte IS NOT NULL THEN f.DL_MontantHT ELSE 0 END) AS ca_covered
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE dom.DO_Domaine = 0
        AND d.annee = 2024
        AND f.DL_CMUP IS NOT NULL
        AND f.DL_CMUP > 0
        AND f.DL_Qte IS NOT NULL
    """
    calc = conn.execute(text(calc_sql)).fetchone()
    
    original_margin = float(calc.original_margin)
    true_margin = float(calc.true_margin)
    ca_covered = float(calc.ca_covered)
    
    original_pct = (original_margin / ca_covered * 100)
    true_pct = (true_margin / ca_covered * 100)
    
    print("\n--- MARGIN CALCULATIONS ---")
    print(f"CA Covered by Cost: {ca_covered:,.2f} DT")
    print(f"Original Margin Sum (Profitable rows only): {original_margin:,.2f} DT | Percentage: {original_pct:.4f}%")
    print(f"True Margin Sum (Including losses & break-even): {true_margin:,.2f} DT | Percentage: {true_pct:.4f}%")
    print(f"Difference: {original_margin - true_margin:,.2f} DT ({original_pct - true_pct:.4f} percentage points)")
