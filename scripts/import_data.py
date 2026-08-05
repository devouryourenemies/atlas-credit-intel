#!/usr/bin/env python3
"""
Import research JSON files into the O&G Credit Intelligence database.
Processes output from the parallel research subagents.
"""
import json
import os
import sys
import glob
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'og_credit_intel.db')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')

SECTOR_MAP = {
    'upstream': 'upstream',
    'midstream': 'midstream',
    'downstream': 'downstream',
    'integrated': 'integrated',
    'oilfield_services': 'oilfield_services',
    'exploration_production': 'upstream',
    'e&p': 'upstream',
    'ep': 'upstream',
    'pipeline': 'midstream',
    'gathering_processing': 'midstream',
    'lng': 'midstream',
    'refining': 'downstream',
    'marketing': 'downstream',
    'diversified': 'diversified',
}

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def upsert_company(conn, company):
    """Insert or update a company record."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    existing = conn.execute(
        "SELECT id FROM companies WHERE company_name = ?", 
        (company['company_name'],)
    ).fetchone()
    
    if existing:
        company_id = existing[0]
        # Update existing
        updates = []
        params = []
        for field in ['ticker', 'headquarters_city', 'headquarters_state_province', 
                      'country', 'sector', 'subsector', 'public_private',
                      'pe_backed', 'pe_firm_name', 'ebitda_most_recent', 
                      'ebitda_fiscal_year', 'ebitda_source', 'ebitda_notes',
                      'revenue_most_recent', 'total_debt', 'market_cap',
                      'enterprise_value', 'credit_rating', 'rating_agency',
                      'source_url', 'notes']:
            col = field
            val = company.get(field)
            if val is not None:
                updates.append(f"{col} = ?")
                params.append(val)
        
        if updates:
            updates.append("last_updated = ?")
            params.append(now)
            params.append(company_id)
            conn.execute(
                f"UPDATE companies SET {', '.join(updates)} WHERE id = ?",
                params
            )
    else:
        # Insert new
        hq_state = company.get('headquarters_state') or company.get('headquarters_state_province')
        sector = SECTOR_MAP.get(company.get('sector', '').lower(), company.get('sector'))
        
        conn.execute("""
            INSERT INTO companies (
                company_name, ticker, headquarters_city, headquarters_state_province,
                country, sector, subsector, public_private, pe_backed, pe_firm_name,
                ebitda_most_recent, ebitda_fiscal_year, ebitda_source, ebitda_notes,
                revenue_most_recent, total_debt, market_cap, enterprise_value,
                credit_rating, rating_agency, source_url, notes, last_updated, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company['company_name'],
            company.get('ticker'),
            company.get('headquarters_city'),
            hq_state,
            company.get('country', 'US'),
            sector,
            company.get('subsector'),
            company.get('public_private', 'public'),
            int(company.get('pe_backed', 0)),
            company.get('pe_firm_name'),
            company.get('ebitda_most_recent'),
            company.get('ebitda_fiscal_year'),
            company.get('ebitda_source'),
            company.get('ebitda_notes'),
            company.get('revenue_most_recent'),
            company.get('total_debt'),
            company.get('market_cap'),
            company.get('enterprise_value'),
            company.get('credit_rating'),
            company.get('rating_agency'),
            company.get('source_url'),
            company.get('notes'),
            now,
            now
        ))
        company_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    # Process credit facilities
    for fac in company.get('facilities', []):
        existing_fac = conn.execute("""
            SELECT id FROM credit_facilities 
            WHERE company_id = ? AND facility_name = ? AND facility_size = ?
        """, (company_id, fac.get('facility_name', ''), fac.get('facility_size'))).fetchone()
        
        if not existing_fac:
            conn.execute("""
                INSERT INTO credit_facilities (
                    company_id, facility_type, facility_name, currency,
                    facility_size, tenor_months, maturity_date, drawn_amount,
                    pricing_base, margin_spread_bps, commitment_fee_bps,
                    lc_subfacility, covenants, administrative_agent,
                    lead_arrangers, syndication_status, credit_agreement_filed,
                    sec_filing_url, source, notes, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                fac.get('facility_type', 'revolving_credit'),
                fac.get('facility_name'),
                fac.get('currency', 'USD'),
                fac.get('facility_size'),
                fac.get('tenor_months'),
                fac.get('maturity_date'),
                fac.get('drawn_amount'),
                fac.get('pricing_base'),
                fac.get('margin_spread_bps'),
                fac.get('commitment_fee_bps'),
                fac.get('lc_subfacility'),
                fac.get('covenants'),
                fac.get('administrative_agent'),
                fac.get('lead_arrangers'),
                fac.get('syndication_status', 'active'),
                fac.get('credit_agreement_filed', 0),
                fac.get('sec_filing_url'),
                fac.get('source'),
                fac.get('notes'),
                now
            ))
    
    # Process executives
    for exec_ in company.get('executives', []):
        existing_exec = conn.execute("""
            SELECT id FROM executives 
            WHERE company_id = ? AND name = ? AND title = ?
        """, (company_id, exec_['name'], exec_['title'])).fetchone()
        
        if not existing_exec:
            conn.execute("""
                INSERT INTO executives (company_id, name, title, office_city, office_state_province, office_country, source, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                exec_['name'],
                exec_['title'],
                exec_.get('office_city'),
                exec_.get('office_state') or exec_.get('office_state_province'),
                exec_.get('office_country', 'US'),
                exec_.get('source'),
                now
            ))
    
    return company_id

def import_all():
    conn = get_conn()
    total_companies = 0
    total_facilities = 0
    total_execs = 0
    
    json_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, 'research_*.json')))
    
    if not json_files:
        print(f"No research JSON files found in {OUTPUT_DIR}")
        print("Run the research subagents first, then come back to import.")
        return
    
    for filepath in json_files:
        filename = os.path.basename(filepath)
        print(f"Importing {filename}...")
        
        with open(filepath) as f:
            data = json.load(f)
        
        companies = data.get('companies', [])
        if not companies:
            print(f"  No companies found in {filename}, skipping.")
            continue
        
        for c in companies:
            try:
                company_id = upsert_company(conn, c)
                total_companies += 1
                
                fac_count = len(c.get('facilities', []))
                exec_count = len(c.get('executives', []))
                total_facilities += fac_count
                total_execs += exec_count
                
                print(f"  ✓ {c['company_name']} — {fac_count} facilities, {exec_count} execs")
            except Exception as e:
                print(f"  ✗ Error importing {c.get('company_name', 'unknown')}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*50}")
    print(f"Import complete: {total_companies} companies, {total_facilities} facilities, {total_execs} executives")
    print(f"{'='*50}")

if __name__ == '__main__':
    import_all()
