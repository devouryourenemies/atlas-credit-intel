#!/usr/bin/env python3
"""
O&G Credit Intelligence System — Database Schema & Setup
Tracks US/Canadian oil & gas companies, their credit facilities, and C-suite locations.
"""
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'og_credit_intel.db')

SCHEMA_SQL = """
-- Companies: oil and gas companies headquartered in US or Canada
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL UNIQUE,
    ticker TEXT,
    headquarters_city TEXT,
    headquarters_state_province TEXT,
    country TEXT NOT NULL DEFAULT 'US',
    sector TEXT CHECK(sector IN ('upstream', 'midstream', 'downstream', 'integrated', 'oilfield_services', 'diversified')),
    subsector TEXT,
    public_private TEXT CHECK(public_private IN ('public', 'private', 'subsidiary')),
    pe_backed INTEGER DEFAULT 0,
    pe_firm_name TEXT,
    ebitda_most_recent REAL,
    ebitda_fiscal_year TEXT,
    ebitda_source TEXT,
    ebitda_notes TEXT,
    revenue_most_recent REAL,
    total_debt REAL,
    market_cap REAL,
    enterprise_value REAL,
    credit_rating TEXT,
    rating_agency TEXT,
    source_url TEXT,
    notes TEXT,
    last_updated TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Credit facilities (RCs, Term Loans, etc.)
CREATE TABLE IF NOT EXISTS credit_facilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    facility_type TEXT CHECK(facility_type IN ('revolving_credit', 'term_loan_a', 'term_loan_b', 'term_loan', 'bridge_loan', 'delayed_draw', 'other')),
    facility_name TEXT,
    currency TEXT DEFAULT 'USD',
    facility_size REAL,  -- in millions
    tenor_months INTEGER,
    maturity_date TEXT,
    drawn_amount REAL,
    pricing_base TEXT CHECK(pricing_base IN ('SOFR', 'LIBOR', 'Base_Rate', 'Prime', 'fixed')),
    margin_spread_bps INTEGER,  -- basis points over base
    commitment_fee_bps INTEGER,
    lc_subfacility REAL,
    covenants TEXT,
    administrative_agent TEXT,
    lead_arrangers TEXT,
    syndication_status TEXT CHECK(syndication_status IN ('active', 'amended', 'repaid', 'terminated', 'upsized', 'extended')),
    credit_agreement_filed INTEGER DEFAULT 0,
    sec_filing_url TEXT,
    source TEXT,
    notes TEXT,
    last_updated TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

-- C-suite executives
CREATE TABLE IF NOT EXISTS executives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    office_city TEXT,
    office_state_province TEXT,
    office_country TEXT DEFAULT 'US',
    source TEXT,
    last_updated TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

-- Monitoring log (for cron job output tracking)
CREATE TABLE IF NOT EXISTS monitoring_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT DEFAULT (datetime('now')),
    job_name TEXT,
    source TEXT,
    items_found INTEGER,
    details TEXT,
    status TEXT CHECK(status IN ('success', 'partial', 'failed'))
);

-- News / deal tracking
CREATE TABLE IF NOT EXISTS deal_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    headline TEXT NOT NULL,
    url TEXT,
    source TEXT,
    published_date TEXT,
    deal_type TEXT CHECK(deal_type IN ('new_facility', 'amendment', 'upsize', 'repayment', 'refinancing', 'acquisition', 'divestiture', 'rating_change', 'earnings', 'other')),
    summary TEXT,
    captured_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL
);

-- For efficient lookups
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS idx_companies_country ON companies(country);
CREATE INDEX IF NOT EXISTS idx_companies_pe_backed ON companies(pe_backed);
CREATE INDEX IF NOT EXISTS idx_facilities_company ON credit_facilities(company_id);
CREATE INDEX IF NOT EXISTS idx_facilities_maturity ON credit_facilities(maturity_date);
CREATE INDEX IF NOT EXISTS idx_executives_company ON executives(company_id);
CREATE INDEX IF NOT EXISTS idx_deal_news_date ON deal_news(published_date);
"""

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn

def export_csv(output_path=None):
    """Export the full database to CSV files."""
    import csv
    conn = sqlite3.connect(DB_PATH)
    base = output_path or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    os.makedirs(base, exist_ok=True)
    
    for table in ['companies', 'credit_facilities', 'executives', 'deal_news']:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        cols = [desc[0] for desc in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        filepath = os.path.join(base, f"{table}.csv")
        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"Exported {len(rows)} rows to {filepath}")
    conn.close()

def generate_report():
    """Generate a market summary report."""
    conn = sqlite3.connect(DB_PATH)
    
    total = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    by_sector = conn.execute("SELECT sector, COUNT(*) FROM companies GROUP BY sector").fetchall()
    pe_count = conn.execute("SELECT COUNT(*) FROM companies WHERE pe_backed=1").fetchone()[0]
    facilities = conn.execute("""
        SELECT c.company_name, cf.facility_type, cf.facility_size, cf.maturity_date, cf.margin_spread_bps
        FROM credit_facilities cf JOIN companies c ON cf.company_id = c.id
        WHERE cf.syndication_status IN ('active', 'amended', 'upsized', 'extended')
        ORDER BY cf.maturity_date
    """).fetchall()
    
    report = f"""# O&G Credit Intelligence Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Coverage Summary
- Total companies tracked: {total}
- PE-backed companies: {pe_count}
- Credit facilities tracked: {len(facilities)}

## Sector Breakdown
"""
    for sector, count in by_sector:
        report += f"- {sector}: {count}\n"
    
    report += "\n## Active Credit Facilities\n\n"
    report += "| Company | Type | Size ($M) | Maturity | Margin (bps) |\n"
    report += "|---------|------|-----------|----------|-------------|\n"
    for row in facilities:
        report += f"| {row[0]} | {row[1]} | ${row[2]:,.0f}M | {row[3] or 'TBD'} | {row[4]} bps |\n"
    
    conn.close()
    return report

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'export':
        export_csv()
    elif len(sys.argv) > 1 and sys.argv[1] == 'report':
        print(generate_report())
    else:
        init_db()
        print(f"Database initialized at {DB_PATH}")
