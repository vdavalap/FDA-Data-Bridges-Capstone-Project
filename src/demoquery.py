"""
Run: python3 src/query_cli.py "Texas"
It prints up to 50 recent inspections where firm_name contains your text.
"""

from pathlib import Path
import sqlite3
import sys

DB = Path(__file__).resolve().parents[1] / "db" / "state_demo.db"

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 src/demoquery.py <substring>")
        sys.exit(1)

    needle = sys.argv[1]
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        SELECT inspection_id, firm_name, inspection_date, inspection_type
        FROM inspections
        WHERE firm_name LIKE '%' || ? || '%'
        ORDER BY inspection_date DESC
        LIMIT 50
    """, (needle,))
    for row in cur.fetchall():
        print(row)
    con.close()

if __name__ == "__main__":
    main()
