#!/usr/bin/env python3
"""
Atlas Credit Intelligence - WhatsApp Delivery Script
Formats credit intel data for WhatsApp messages.
Run via cron or on-demand to send updates.
"""

import sqlite3
import json
from datetime import datetime, timedelta

DB_PATH = "/Users/Vancito/Documents/og-credit-intel/data/og_credit_intel.db"

def get_db():
    return sqlite3.connect(DB_PATH)

def get_texas_summary():
    """Get summary of Texas companies for WhatsApp."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Texas company count and stats
    cursor.execute('''SELECT COUNT(*), SUM(ebitda_most_recent) 
                      FROM companies WHERE headquarters_state_province = 'TX' ''')
    count, total_ebitda = cursor.fetchone()
    
    # Sector breakdown
    cursor.execute('''SELECT sector, COUNT(*) 
                      FROM companies WHERE headquarters_state_province = 'TX'
                      GROUP BY sector ORDER BY COUNT(*) DESC''')
    sectors = cursor.fetchall()
    
    # Facilities maturing soon
    cursor.execute('''SELECT c.company_name, cf.facility_name, cf.facility_size, 
                      cf.maturity_date, cf.margin_spread_bps
                      FROM credit_facilities cf 
                      JOIN companies c ON cf.company_id = c.id
                      WHERE c.headquarters_state_province = 'TX'
                      AND cf.maturity_date <= date('now', '+12 months')
                      ORDER BY cf.maturity_date''')
    maturities = cursor.fetchall()
    
    conn.close()
    
    ebitda_str = f"${total_ebitda/1e9:.1f}B" if total_ebitda else "N/A"
    sector_str = "\n".join([f"  {s}: {c}" for s, c in sectors])
    
    msg = f"""ATLAS CREDIT INTELLIGENCE
Texas Energy Finance Update
{datetime.now().strftime('%B %d, %Y')}

COMPANIES: {count} Texas-headquartered
AGGREGATE EBITDA: {ebitda_str}

SECTOR BREAKDOWN:
{sector_str}"""
    
    if maturities:
        msg += "\n\nFACILITIES MATURING IN 12 MONTHS:"
        for name, facility, size, maturity, margin in maturities:
            size_str = f"${size:.0f}M" if size else "N/A"
            margin_str = f"{margin} bps" if margin else "N/A"
            msg += f"\n  {name}"
            msg += f"\n    {facility}"
            msg += f"\n    Size: {size_str} | Maturity: {maturity}"
            msg += f"\n    Margin: {margin_str}"
    else:
        msg += "\n\nNo facilities maturing in the next 12 months."
    
    msg += f"\n\nFull data: devouryourenemies.github.io/atlas-credit-intel/"
    
    return msg

def get_company_lookup(company_name):
    """Look up a specific company."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''SELECT company_name, ticker, headquarters_city, 
                      headquarters_state_province, country, sector, 
                      ebitda_most_recent, credit_rating, pe_backed, pe_firm_name
                      FROM companies 
                      WHERE company_name LIKE ? OR ticker LIKE ?
                      LIMIT 1''', (f'%{company_name}%', f'%{company_name}%'))
    company = cursor.fetchone()
    
    if not company:
        conn.close()
        return f"Company '{company_name}' not found in database."
    
    name, ticker, city, state, country, sector, ebitda, rating, pe_backed, pe_firm = company
    
    # Get facilities
    cursor.execute('''SELECT facility_type, facility_name, facility_size, 
                      maturity_date, margin_spread_bps, pricing_base, lead_arrangers
                      FROM credit_facilities cf 
                      JOIN companies c ON cf.company_id = c.id
                      WHERE c.company_name = ?''', (name,))
    facilities = cursor.fetchall()
    
    # Get executives
    cursor.execute('''SELECT name, title, office_city, office_state_province
                      FROM executives 
                      WHERE company_id = (SELECT id FROM companies WHERE company_name = ?)''', (name,))
    execs = cursor.fetchall()
    
    conn.close()
    
    ebitda_str = f"${ebitda/1e9:.1f}B" if ebitda else "N/A"
    location = f"{city}, {state}" if state else f"{city}, {country}"
    
    msg = f"""{name} ({ticker})
{location} | {sector.title()}
EBITDA: {ebitda_str} | Rating: {rating or 'N/A'}"""
    
    if pe_backed and pe_firm:
        msg += f"\nPE Backing: {pe_firm}"
    
    if facilities:
        msg += "\n\nCREDIT FACILITIES:"
        for ftype, fname, fsize, maturity, margin, pricing, arrangers in facilities:
            size_str = f"${fsize:.0f}M" if fsize else "N/A"
            margin_str = f"{margin} bps" if margin else "N/A"
            msg += f"\n  {fname}"
            msg += f"\n  Type: {ftype.replace('_', ' ').title()}"
            msg += f"\n  Size: {size_str} | Maturity: {maturity or 'N/A'}"
            msg += f"\n  Pricing: {pricing or 'SOFR'} + {margin_str}"
            if arrangers:
                msg += f"\n  Arrangers: {arrangers}"
    else:
        msg += "\n\nNo credit facilities in database."
    
    if execs:
        msg += "\n\nKEY CONTACTS:"
        for ename, etitle, ecity, estate in execs[:5]:
            eloc = f"{ecity}, {estate}" if estate else ecity
            msg += f"\n  {ename}, {etitle}"
            msg += f"\n  {eloc}"
    
    return msg

def get_refinancing_targets():
    """Get companies with facilities maturing in 12 months."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''SELECT c.company_name, c.ticker, c.sector,
                      cf.facility_name, cf.facility_size, cf.maturity_date, 
                      cf.margin_spread_bps, c.ebitda_most_recent
                      FROM credit_facilities cf 
                      JOIN companies c ON cf.company_id = c.id
                      WHERE cf.maturity_date <= date('now', '+12 months')
                      AND cf.maturity_date >= date('now')
                      ORDER BY cf.maturity_date''')
    targets = cursor.fetchall()
    conn.close()
    
    if not targets:
        return "No facilities maturing in the next 12 months."
    
    msg = f"REFINANCING TARGETS (Next 12 Months)\n"
    msg += f"Generated: {datetime.now().strftime('%Y-%m-%d')}\n\n"
    
    for name, ticker, sector, facility, size, maturity, margin, ebitda in targets:
        size_str = f"${size:.0f}M" if size else "N/A"
        margin_str = f"{margin} bps" if margin else "N/A"
        ebitda_str = f"${ebitda/1e9:.1f}B" if ebitda else "N/A"
        
        msg += f"{name} ({ticker})\n"
        msg += f"  {facility}\n"
        msg += f"  Size: {size_str} | Matures: {maturity}\n"
        msg += f"  Current Margin: {margin_str}\n"
        msg += f"  EBITDA: {ebitda_str} | Sector: {sector}\n\n"
    
    msg += f"Total targets: {len(targets)}\n"
    msg += f"Full data: devouryourenemies.github.io/atlas-credit-intel/"
    
    return msg

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "summary":
            print(get_texas_summary())
        elif cmd == "lookup" and len(sys.argv) > 2:
            print(get_company_lookup(sys.argv[2]))
        elif cmd == "refi":
            print(get_refinancing_targets())
        else:
            print("Usage: credit_intel.py [summary|lookup <company>|refi]")
    else:
        print(get_texas_summary())
