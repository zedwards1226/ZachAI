import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "weatheralpha.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, timestamp, city, market_id, side, contracts,
               price_cents, edge, kelly_frac, stake_usd, paper,
               status, pnl_usd, resolved_at, notes
        FROM trades
        ORDER BY id DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No trades found.")
        return

    print(f"{'ID':>4}  {'Timestamp':<20}  {'City':<5}  {'Side':<4}  "
          f"{'Qty':>3}  {'Price':>5}  {'Edge':>6}  {'Stake':>7}  "
          f"{'Status':<9}  {'PnL':>7}  {'Paper'}")
    print("-" * 100)

    for r in reversed(rows):  # show oldest-first within the 20
        pnl = f"${r['pnl_usd']:+.2f}" if r['pnl_usd'] is not None else "   —   "
        paper = "PAPER" if r['paper'] else "LIVE"
        print(
            f"{r['id']:>4}  {r['timestamp']:<20}  {r['city']:<5}  {r['side']:<4}  "
            f"{r['contracts']:>3}  {r['price_cents']:>4}¢  {r['edge']:>+.3f}  "
            f"${r['stake_usd']:>6.2f}  {r['status']:<9}  {pnl:>7}  {paper}"
        )

if __name__ == "__main__":
    main()
