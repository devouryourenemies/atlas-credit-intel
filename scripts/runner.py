#!/usr/bin/env python3
"""
O&G Credit Intelligence — Master Runner
Orchestrates: research → import → export → report
Also handles: screening, SEC lookups, CSV exports
"""
import os
import sys
import subprocess
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, 'scripts')
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

def run_script(script_name, *args):
    """Run one of our Python scripts and return the output."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [sys.executable, script_path] + list(args)
    print(f"▶ Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
    if result.returncode != 0:
        print(f"  ✗ Failed with code {result.returncode}")
    return result.returncode

def full_refresh():
    """Full pipeline: init DB, import all research, export everything."""
    print(f"{'='*60}")
    print(f"O&G CREDIT INTELLIGENCE — FULL REFRESH")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Step 1: Initialize DB
    print("--- Step 1: Initialize Database ---")
    run_script('create_db.py')
    print()
    
    # Step 2: Check for research files
    print("--- Step 2: Check Research Data ---")
    json_files = sorted([
        f for f in os.listdir(OUTPUT_DIR) 
        if f.startswith('research_') and f.endswith('.json')
    ])
    if json_files:
        print(f"Found research files: {', '.join(json_files)}")
        run_script('import_data.py')
    else:
        print("No research JSON files found in output/.")
        print("Run research subagents first via Hermes delegate_task.")
    print()
    
    # Step 3: Export & Report
    print("--- Step 3: Generate Exports & Reports ---")
    run_script('export_report.py')
    print()
    
    print(f"{'='*60}")
    print(f"REFRESH COMPLETE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

def quick_stats():
    """Show current database statistics."""
    import sqlite3
    db_path = os.path.join(DATA_DIR, 'og_credit_intel.db')
    if not os.path.exists(db_path):
        print("Database not initialized. Run 'full_refresh' first.")
        return
    
    conn = sqlite3.connect(db_path)
    
    total = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    by_sector = conn.execute("""
        SELECT sector, COUNT(*) FROM companies GROUP BY sector ORDER BY COUNT(*) DESC
    """).fetchall()
    facilities = conn.execute("SELECT COUNT(*) FROM credit_facilities").fetchone()[0]
    execs = conn.execute("SELECT COUNT(*) FROM executives").fetchone()[0]
    pe_count = conn.execute("SELECT COUNT(*) FROM companies WHERE pe_backed=1").fetchone()[0]
    
    total_ebitda = conn.execute("""
        SELECT SUM(ebitda_most_recent) FROM companies WHERE ebitda_most_recent IS NOT NULL
    """).fetchone()[0]
    
    active_facilities = conn.execute("""
        SELECT COUNT(*), SUM(facility_size) FROM credit_facilities 
        WHERE syndication_status IN ('active', 'amended', 'upsized', 'extended')
    """).fetchone()
    
    print(f"\n{'='*50}")
    print(f"O&G CREDIT INTELLIGENCE — DATABASE STATS")
    print(f"{'='*50}")
    print(f"Total companies:           {total}")
    print(f"  PE-backed:               {pe_count}")
    print(f"  Total tracked EBITDA:    ${total_ebitda:,.0f}" if total_ebitda else "")
    print(f"Credit facilities:         {facilities}")
    print(f"  Active:                  {active_facilities[0]}")
    print(f"  Active facility size:    ${active_facilities[1]:,.0f}M" if active_facilities[1] else "")
    print(f"C-suite executives:        {execs}")
    print(f"\nBy sector:")
    for sector, cnt in by_sector:
        print(f"  {sector:30s} {cnt}")
    
    conn.close()
    print(f"{'='*50}\n")

def screen_companies(min_ebitda=80, sector=None, country=None):
    """Screen companies by criteria."""
    import sqlite3
    db_path = os.path.join(DATA_DIR, 'og_credit_intel.db')
    if not os.path.exists(db_path):
        print("No database. Run full_refresh first.")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    where_clauses = []
    params = []
    
    if min_ebitda:
        where_clauses.append("(c.ebitda_most_recent >= ? OR c.pe_backed = 1)")
        params.append(min_ebitda * 1_000_000)  # Convert to raw number
    
    if sector:
        where_clauses.append("c.sector = ?")
        params.append(sector)
    
    if country:
        where_clauses.append("c.country = ?")
        params.append(country)
    
    where = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    rows = conn.execute(f"""
        SELECT 
            c.company_name, c.ticker, c.country, c.sector, c.ebitda_most_recent,
            c.ebitda_fiscal_year, c.pe_backed, c.pe_firm_name, c.credit_rating,
            c.headquarters_city, c.headquarters_state_province
        FROM companies c
        WHERE {where}
        ORDER BY c.ebitda_most_recent DESC NULLS LAST
    """, params).fetchall()
    
    print(f"\n{'='*100}")
    print(f"COMPANY SCREEN: EBITDA ≥ ${min_ebitda}M{' OR PE-backed' if min_ebitda else ''}")
    if sector: print(f"Sector: {sector}")
    if country: print(f"Country: {country}")
    print(f"{'='*100}")
    print(f"{'Company':30s} {'Ticker':8s} {'Country':4s} {'Sector':20s} {'EBITDA ($M)':15s} {'PE Backing':25s} {'Rating':8s}")
    print(f"{'-'*30} {'-'*8} {'-'*4} {'-'*20} {'-'*15} {'-'*25} {'-'*8}")
    
    for r in rows:
        ebitda_str = f"${r['ebitda_most_recent']/1_000_000:,.0f}M" if r['ebitda_most_recent'] else 'N/A'
        pe_str = r['pe_firm_name'] if r['pe_backed'] and r['pe_firm_name'] else ('Yes' if r['pe_backed'] else '')
        print(f"{r['company_name']:30s} {r['ticker'] or '':8s} {r['country']:4s} {r['sector'] or '':20s} {ebitda_str:15s} {pe_str:25s} {r['credit_rating'] or '':8s}")
    
    print(f"\nTotal: {len(rows)} companies")
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 runner.py [full_refresh|stats|screen]")
        sys.exit(1)
    
    command = sys.argv[1]
    if command == 'full_refresh':
        full_refresh()
    elif command == 'stats':
        quick_stats()
    elif command == 'screen':
        min_ebitda = int(sys.argv[2]) if len(sys.argv) > 2 else 80
        sector = sys.argv[3] if len(sys.argv) > 3 else None
        country = sys.argv[4] if len(sys.argv) > 4 else None
        screen_companies(min_ebitda, sector, country)
    else:
        print(f"Unknown command: {command}")
        print("Commands: full_refresh, stats, screen [min_ebitda] [sector] [country]")
