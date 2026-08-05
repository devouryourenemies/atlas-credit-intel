#!/usr/bin/env python3
"""
O&G Credit Intelligence — Deal Origination Screener
For Energy Finance bankers: screens companies by refinancing need,
maturity proximity, covenant headroom, and relationship opportunity.

Usage:
  python3 screener.py                    # Full screen
  python3 screener.py --maturities-12mo  # Deals maturing in 12 months
  python3 screener.py --pe-backed        # Only PE-backed companies
  python3 screener.py --sector upstream  # Filter by sector
  python3 screener.py --target-excel     # Output ready for Excel
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, date
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'og_credit_intel.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def format_num(val, prefix='$', suffix=''):
    if val is None:
        return '—'
    if isinstance(val, (int, float)):
        if abs(val) >= 1_000_000_000:
            return f"{prefix}{val/1_000_000_000:,.1f}B{suffix}"
        elif abs(val) >= 1_000_000:
            return f"{prefix}{val/1_000_000:,.0f}M{suffix}"
        else:
            return f"{prefix}{val:,.0f}{suffix}"
    return str(val)

def refinancing_opportunities(months_window=12):
    """
    Identifies companies with credit facilities maturing within the window.
    These are refinancing/amend-and-extend candidates.
    """
    conn = get_conn()
    
    today = date.today()
    
    rows = conn.execute("""
        SELECT 
            c.company_name, c.ticker, c.sector, c.country,
            c.ebitda_most_recent, c.credit_rating,
            cf.facility_name, cf.facility_type, cf.facility_size,
            cf.maturity_date, cf.margin_spread_bps, cf.pricing_base,
            cf.lead_arrangers, cf.syndication_status,
            c.id as company_id
        FROM credit_facilities cf
        JOIN companies c ON cf.company_id = c.id
        WHERE cf.maturity_date IS NOT NULL
          AND cf.maturity_date >= date('now')
          AND cf.syndication_status IN ('active', 'amended', 'upsized', 'extended')
        ORDER BY cf.maturity_date ASC
    """).fetchall()
    
    opportunities = []
    for r in rows:
        try:
            mat_date = datetime.strptime(r['maturity_date'], '%Y-%m-%d').date()
            months_to_mat = (mat_date.year - today.year) * 12 + (mat_date.month - today.month)
            
            if months_to_mat <= months_window:
                # Check if we have PE info
                pe_info = conn.execute("""
                    SELECT pe_backed, pe_firm_name FROM companies WHERE id = ?
                """, (r['company_id'],)).fetchone()
                
                opportunities.append({
                    'company': r['company_name'],
                    'ticker': r['ticker'] or '',
                    'sector': r['sector'],
                    'country': r['country'],
                    'ebitda': r['ebitda_most_recent'],
                    'rating': r['credit_rating'] or '',
                    'facility_name': r['facility_name'] or '',
                    'facility_type': r['facility_type'],
                    'facility_size': r['facility_size'],
                    'maturity_date': r['maturity_date'],
                    'months_remaining': months_to_mat,
                    'current_margin': r['margin_spread_bps'],
                    'pricing_base': r['pricing_base'] or '',
                    'lead_arrangers': r['lead_arrangers'] or '',
                    'pe_backed': pe_info['pe_backed'] if pe_info else 0,
                    'pe_firm': pe_info['pe_firm_name'] if pe_info else '',
                    'opportunity_type': 'Refinancing',
                })
        except (ValueError, TypeError):
            continue
    
    return opportunities

def pe_portfolio_companies():
    """List PE-backed companies and their credit facilities."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, 
               cf.facility_type, cf.facility_size, cf.maturity_date, cf.margin_spread_bps,
               cf.lead_arrangers
        FROM companies c
        LEFT JOIN credit_facilities cf ON cf.company_id = c.id AND cf.syndication_status IN ('active', 'amended', 'upsized', 'extended')
        WHERE c.pe_backed = 1
        ORDER BY c.pe_firm_name, c.company_name
    """).fetchall()
    
    grouped = defaultdict(list)
    for r in rows:
        firm = r['pe_firm_name'] or 'Unknown PE'
        grouped[firm].append({
            'company': r['company_name'],
            'ticker': r['ticker'],
            'sector': r['sector'],
            'ebitda': r['ebitda_most_recent'],
            'facility_type': r['facility_type'],
            'facility_size': r['facility_size'],
            'maturity': r['maturity_date'],
            'margin': r['margin_spread_bps'],
            'arrangers': r['lead_arrangers'],
        })
    
    return dict(grouped)

def rate_thesis_opportunities():
    """
    Finds companies with credit rating that signals potential upgrade
    or where the bank could provide a better execution.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT company_name, ticker, sector, ebitda_most_recent, 
               total_debt, credit_rating, rating_agency, market_cap
        FROM companies
        WHERE credit_rating IS NOT NULL
        ORDER BY 
            CASE credit_rating
                WHEN 'AAA' THEN 1 WHEN 'AA+' THEN 2 WHEN 'AA' THEN 3 WHEN 'AA-' THEN 4
                WHEN 'A+' THEN 5 WHEN 'A' THEN 6 WHEN 'A-' THEN 7
                WHEN 'BBB+' THEN 8 WHEN 'BBB' THEN 9 WHEN 'BBB-' THEN 10
                WHEN 'BB+' THEN 11 WHEN 'BB' THEN 12 WHEN 'BB-' THEN 13
                WHEN 'B+' THEN 14 WHEN 'B' THEN 15 WHEN 'B-' THEN 16
                ELSE 99
            END
    """).fetchall()
    
    return rows

def screen_for_targeting():
    """
    Comprehensive targeting report combining all signals.
    """
    conn = get_conn()
    
    # Summary stats
    stats = {}
    stats['total_companies'] = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    stats['total_facilities'] = conn.execute("SELECT COUNT(*) FROM credit_facilities").fetchone()[0]
    stats['by_sector'] = dict(conn.execute(
        "SELECT sector, COUNT(*) FROM companies GROUP BY sector"
    ).fetchall())
    stats['by_country'] = dict(conn.execute(
        "SELECT country, COUNT(*) FROM companies GROUP BY country"
    ).fetchall())
    stats['pe_count'] = conn.execute("SELECT COUNT(*) FROM companies WHERE pe_backed=1").fetchone()[0]
    
    print(f"""
{'='*80}
O&G CREDIT ORIGINATION — TARGETING SCREEN
{'='*80}

DATABASE COVERAGE
  Companies tracked    : {stats['total_companies']}
  PE-backed            : {stats['pe_count']}
  Credit facilities    : {stats['total_facilities']}
  By sector: {', '.join(f'{k}={v}' for k,v in sorted(stats['by_sector'].items()))}

REFINANCING OPPORTUNITIES (Next 12 Months)
""")
    
    refi_opps = refinancing_opportunities(12)
    if refi_opps:
        print(f"  {'Company':30s} {'Ticker':8s} {'Facility':20s} {'Size':12s} {'Matures':12s} {'Mo':4s} {'Margin':8s}")
        print(f"  {'-'*30} {'-'*8} {'-'*20} {'-'*12} {'-'*12} {'-'*4} {'-'*8}")
        for o in refi_opps:
            size_str = format_num(o['facility_size'])
            margin_str = f"{o['current_margin']}bps" if o['current_margin'] else '—'
            print(f"  {o['company']:30s} {o['ticker']:8s} {o['facility_type']:20s} {size_str:12s} {o['maturity_date']:12s} {o['months_remaining']:3d}mo {margin_str:8s}")
        print(f"\n  Total: {len(refi_opps)} refinancing opportunities in next 12 months")
    else:
        print("  No upcoming maturities found in database.\n")
    
    print(f"""
PE-BACKED COMPANIES
""")
    pe_groups = pe_portfolio_companies()
    if pe_groups:
        for firm, companies in sorted(pe_groups.items()):
            print(f"  {firm}:")
            for c in companies:
                size_str = format_num(c['facility_size']) if c['facility_size'] else '—'
                margin_str = f"@{c['margin']}bps" if c['margin'] else ''
                print(f"    • {c['company']} {c['ticker'] or ''} ({c['sector']}) — EBITDA: {format_num(c['ebitda'])} — {c['facility_type'] or ''} {size_str} {margin_str}")
            print()
    else:
        print("  No PE-backed companies in database.\n")
    
    print(f"""
CREDIT RATING DISTRIBUTION
""")
    rated = rate_thesis_opportunities()
    if rated:
        by_rating = defaultdict(list)
        for r in rated:
            by_rating[r['credit_rating'] or 'Unrated'].append(r)
        
        for rating in ['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-',
                       'BB+','BB','BB-','B+','B','B-']:
            group = by_rating.get(rating, [])
            if group:
                names = ', '.join(f"{c['company_name']} ({c['ticker']})" for c in group[:3])
                if len(group) > 3:
                    names += f" +{len(group)-3} more"
                print(f"  {rating:6s} | {len(group):2d} companies | {names}")
        
        unrated = by_rating.get('Unrated', [])
        if unrated:
            print(f"  {'NR':6s} | {len(unrated):2d} companies")
    
    conn.close()
    
    print(f"\n{'='*80}")
    print(f"ACTIONABLE INSIGHTS")
    print(f"{'='*80}")
    
    if refi_opps:
        total_volume = sum(o['facility_size'] for o in refi_opps if o['facility_size'])
        print(f"\n  → {len(refi_opps)} facilities totaling {format_num(total_volume)} maturing in 12 months")
        print(f"  → Refinancing / amend-and-extend candidates for your loan book")
    
    print(f"\n  → CSVs ready at: ~/Documents/og-credit-intel/output/")
    print(f"  → Run 'python3 export_report.py' to refresh exports")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    if '--maturities-12mo' in sys.argv:
        opps = refinancing_opportunities(12)
        print(json.dumps([dict(o) for o in opps], indent=2, default=str))
    elif '--pe-backed' in sys.argv:
        pe = pe_portfolio_companies()
        print(json.dumps(pe, indent=2, default=str))
    elif '--sector' in sys.argv:
        idx = sys.argv.index('--sector')
        sector = sys.argv[idx + 1]
        conn = get_conn()
        rows = conn.execute("""
            SELECT company_name, ticker, ebitda_most_recent, pe_backed, pe_firm_name
            FROM companies WHERE sector = ? ORDER BY ebitda_most_recent DESC
        """, (sector,)).fetchall()
        print(f"\nSector: {sector}")
        print(f"{'Company':30s} {'Ticker':8s} {'EBITDA':15s} {'PE':25s}")
        print(f"{'-'*30} {'-'*8} {'-'*15} {'-'*25}")
        for r in rows:
            pe = r['pe_firm_name'] if r['pe_backed'] else ''
            print(f"{r['company_name']:30s} {r['ticker'] or '':8s} {format_num(r['ebitda_most_recent']):15s} {pe:25s}")
        print()
        conn.close()
    elif '--target-excel' in sys.argv:
        # Output tab-separated for easy Excel paste
        opps = refinancing_opportunities(24)
        print("Company\tTicker\tSector\tFacility Type\tSize\tMaturity\tMonths Left\tCurrent Margin\tRating\tPE Backed\tPE Firm")
        for o in opps:
            print(f"{o['company']}\t{o['ticker']}\t{o['sector']}\t{o['facility_type']}\t{o['facility_size']}\t{o['maturity_date']}\t{o['months_remaining']}\t{o['current_margin']}\t{o['rating']}\t{o['pe_backed']}\t{o['pe_firm']}")
    else:
        screen_for_targeting()
