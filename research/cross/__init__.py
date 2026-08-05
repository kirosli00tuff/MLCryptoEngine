"""Stage C.13: cross-sectional funding carry, both legs on one venue.

C.11 tested cash-and-carry — long spot, short perp — and the spot leg's 80 bps
round trip on Kraken or Coinbase dominated every cost figure it produced. This
package tests a different structure entirely: long the perps paying the most
negative funding, short the perps paying the most positive, sized dollar
neutral, with **both legs on Hyperliquid at 1.5 bps a side**. No spot leg
exists, so the expensive venue leaves the trade.

The motivating observation is dispersion rather than level. C.11 measured TNSR
at -32.41% annualised funding against HYPE at +21.60% — a 54 point spread
across instruments on one venue. C.11 treated negative-funding coins as
instruments to avoid; here they are the long leg and that negative funding is
income.

**This is dollar neutral, not delta neutral, and the distinction is the whole
risk.** C.11's structure cancelled price exposure mechanically: the same asset,
long and short, in equal units. Nothing cancels here. The long basket and the
short basket are different coins that can move apart without limit, so price
P&L is a real and possibly dominant term rather than a rounding error.
:mod:`research.cross.portfolio` therefore reports funding income and price
return as separate numbers before combining them, because a positive total
built from a small carry and a large directional bet is not a carry trade.

Module order is the order the question has to be answered in:

``acquire``     free funding and daily-candle history for every perp the venue
                has ever listed, delisted ones included.
``universe``    who was actually tradeable on each date, from the venue's own
                record of publishing funding for them.
``dispersion``  **the gate.** C.11 showed the funding *level* decayed ~85%.
                Dispersion is a different quantity and may not have followed.
                If it compressed too, nothing downstream is worth building.
``portfolio``   construction, turnover, cost, residual price risk, capital.
"""
