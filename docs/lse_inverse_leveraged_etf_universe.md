# LSE Inverse & Leveraged ETF Universe

Reference document for building relative-value (RV) portfolios on the London Stock Exchange using inverse and leveraged ETFs/ETPs. Focus is on liquid names suitable for expressing market and geopolitical event views.

**Style context:** intraday-to-multi-day swing trades expressing macro/geopolitical events via paired LSE-listed ETFs (e.g. long 3OIL.L vs long QQQS.L for an oil-shock-into-tech-weakness Monday open trade). Daily-rebalanced products suit short holding periods; compounding decay punishes multi-week holds.

---

## Issuer Map

Five issuers cover the LSE inverse/leveraged space. Each has a different sweet spot:

| Issuer | Sweet spot | Leverage menu | Notes |
|---|---|---|---|
| **WisdomTree (ex-Boost)** | Broadest range across all asset classes | -1x, -2x, -3x | Workhorse. UCITS, fully collateralised. ~0.75–0.99% TER. Most liquid LSE-native inverse range. |
| **Xtrackers (DWS)** | Plain -1x equity & bond swap ETFs | -1x, -2x | UCITS swap-replicated. Some lines deeper on Xetra/Borsa Italiana than LSE. |
| **Amundi (ex-Lyxor)** | -1x and -2x equity, EU indices | -1x, -2x | EU country exposures. Liquidity often better on Euronext/Xetra. |
| **Société Générale** | 74-product ETP suite, exotic leverage | -2x, -3x, -5x | Includes -5x lines. Tickers SG7x–SG9x LN. Generally less liquid than WisdomTree. |
| **GraniteShares / Leverage Shares** | Single-stock inverse | -3x (some -1x, -2x) | TSLA, NVDA, AAPL, META, MSFT, AMZN, GOOGL, NFLX, AMD, COIN, etc. 0.99% TER. |

---

## WisdomTree (Boost) — Primary Range

Naming convention for index ETPs: numeric prefix = leverage, letter suffix = direction (`L` = long, `S` = short).

### Equity Indices

| Underlying | -1x Short | -2x Short | -3x Short | 3x Long |
|---|---|---|---|---|
| S&P 500 | — | — | **3USS** | 3USL |
| Nasdaq 100 | — | — | **QQQS** | QQQ3 / 3QQL |
| FTSE 100 | **SUK1** | **SUK2** | **3UKS** | 3UKL / LUK2 (2x long) |
| FTSE 250 | **1MCS** | — | — | 2MCL (2x long) |
| Euro Stoxx 50 | — | — | **3SES / 3EUS** | 3LES |
| FTSE MIB (Italy) | — | — | **3ITS** | 3ITL |
| Euro Stoxx Banks | — | — | **3BAS** | 3BAL |
| Russell 2000 | — | — | **3RUS** | 3LRU |
| DAX | — | — (Xtrackers DBPD covers -2x) | — | — |

### Commodities (1x Short ETPs)

| Commodity | -1x Short | -3x Short | 3x Long |
|---|---|---|---|
| WTI Crude | **SOIL** | **3OIS** | 3OIL |
| Brent Crude | **SBRT** | **3BRS** | 3BRL |
| Natural Gas | **SNGA** | **3NGS** | 3NGL |
| Gold | **SBUL** | **3GOS** | 3GOL |
| Silver | **SSIL** | **3SIS** | 3SIL |
| Copper | **SCOP** | **3HCS** | 3HCL |
| Aluminium / Nickel / Zinc | -1x lines exist | — | — |
| Soft commodities (Sugar, Coffee, Wheat, Corn, Soybeans) | -1x lines exist | — | — |

### Rates

| Underlying | -1x Short | -3x Short |
|---|---|---|
| UK Gilts 10Y | **1GIS** | 3GIS |
| US Treasuries 10Y | — | **3TYS** |
| US Treasuries 30Y (Ultra Bond) | — | **UL3S** |
| German Bund 30Y | — | XMWH (cross-listed Xetra) |

---

## Xtrackers — Plain Inverse

Best for clean -1x equity/bond exposure when you don't want compounding noise.

| Product | LSE Ticker | Leverage |
|---|---|---|
| Xtrackers S&P 500 Inverse Daily Swap | **XSPS** | -1x |
| Xtrackers FTSE 100 Short Daily Swap | **XUKS** | -1x |
| Xtrackers ShortDAX Daily | **XSDX** (Xetra primary) | -1x |
| Xtrackers ShortDAX x2 | **DBPD** | -2x |
| Xtrackers S&P 500 2x Leveraged Daily | XS2D | +2x |

---

## Amundi (ex-Lyxor) — EU Country Inverse

Useful for country-specific political/banking risk expressions.

| Product | Notes |
|---|---|
| Amundi MSCI USA Daily (-1x) Inverse | LU1327051279 |
| Amundi S&P 500 Daily -2x Inverse (DSP5) | -2x |
| Amundi FTSE MIB Daily (-1x) Inverse | Italy political/banking exposure |
| Lyxor ShortDAX Daily (-1x) Inverse (C004) | DAX -1x |
| Lyxor double-short Treasuries / Gilts / JGBs | -2x government bonds |

---

## Société Générale — Exotic Leverage

74-product ETP suite. Format: `SGxx LN`. Covers S&P 500, FTSE 100, DAX, Euro Stoxx 50, oil, silver, gold, copper, nat gas, GBP/USD, EUR/USD, JPY/USD at 2x, 3x, and 5x both long and short.

Sample tickers:
- SG78/SG79 — DAX 3x long/short
- SG84/SG85 — FTSE 3x long/short
- SG86/SG87 — FTSE 5x long/short
- SG90/SG91 — S&P 3x long/short
- SG92/SG93 — S&P 5x long/short

---

## Single-Stock Inverse (GraniteShares & Leverage Shares)

For event trades on individual US megacaps. Liquidity meaningful only in TSLA and NVDA names.

| Stock | GraniteShares -3x | Leverage Shares -3x |
|---|---|---|
| Tesla | **3STS** | TS3S |
| Nvidia | 3SNV | **NV3S** |
| Apple | **3SAP** | AP3S |
| Amazon | 3SAM | — |
| Meta | 3SMR | — |
| Microsoft | 3SMS | MS3S |
| Alphabet | 3SGO | — |
| Netflix | 3SNF | — |

GraniteShares lists ~18 US single-stock leveraged/inverse ETPs on LSE. Leverage Shares overlaps and adds AMD, COIN, PLTR, BRK, etc.

---

## Building Blocks → Trade Expressions

Examples of macro/geopolitical events expressible via LSE pairs:

| Thesis | Long leg | Short leg (or inverse long) |
|---|---|---|
| Iran/Hormuz oil shock hits EU industrials | 3OIL | 3SES (Euro Stoxx 50 3x short) |
| ECB hawkish surprise, UK insulated | SUK1 (FTSE 1x short) | 3LES (Euro Stoxx 50 3x long) — i.e. short EU vs neutral UK via paired inverse |
| China reopening fade hits copper | SCOP (Copper 1x short) | SBUL (Gold 1x short, as funding) |
| US debt ceiling stress | 3TYS (UST 3x short) + 3USS (S&P 3x short) | — |
| Italy banking stress | Amundi FTSE MIB -1x | 3BAS (Euro Banks 3x short) |
| UK domestic shock (BoE/fiscal) | 1MCS (FTSE 250 1x short) | — much better domestic expression than FTSE 100 (global earners) |
| Tech-led drawdown, oil bid | 3OIL | QQQS (Nasdaq 3x short) — *the Monday-open intraday-bounce trade* |
| Single-name tech blow-up | NV3S or 3STS | Sector hedge via QQQ3 (3x long Nasdaq) |

---

## Liquidity Hierarchy (for fill-quality)

Rank order for tradeable liquidity on the LSE primary line:

1. **WisdomTree 3x flagships**: 3USL/3USS, QQQ3/QQQS, 3UKL/3UKS, 3OIL/3OIS, 3GOL/3GOS — deepest books
2. **WisdomTree 1x equity shorts**: SUK1, 1MCS — adequate
3. **WisdomTree 1x commodity shorts**: SOIL, SBUL, SSIL, SNGA — adequate, wider spreads
4. **Xtrackers -1x swap ETFs**: XUKS, XSPS — often thin on LSE; check Xetra
5. **GraniteShares/Leverage Shares single-stock**: only TSLA & NVDA inverses meaningful; rest quote-driven
6. **Amundi/Lyxor inverse**: usually thinner on LSE than primary EU listing
7. **Société Générale ETPs**: generally thin

**Rule of thumb:** if a -1x or -2x ETP shows <£500k ADV on LSE, substitute the corresponding WisdomTree 3x at one-third notional for the same exposure with better liquidity.

---

## Key Caveats

- **Daily rebalancing decay**: all leveraged/inverse ETPs reset daily. Multi-day holds in choppy markets erode value. Suits intraday-to-2-day style; avoid >5-day holds without strong directional conviction.
- **TER is paid via NAV drag**, not separately — already in the price path.
- **UCITS-eligible** for all WisdomTree, Xtrackers, Amundi lines. SIPP/ISA-eligible varies by broker.
- **Currency**: most LSE lines available in both GBP and USD share classes (e.g. 3USL = USD; LUS3 = GBP equivalent). Match to your account base currency to avoid FX leakage on entry/exit.
- **Reporting status**: confirm UK reporting fund status for non-ISA/SIPP accounts to avoid offshore-income-gain treatment on disposal.

---

## Sources

- [WisdomTree cross-lists 18 inverse & leveraged Boost ETPs on LSE — ETF Strategy](https://www.etfstrategy.com/wisdomtree-cross-lists-18-inverse-leveraged-boost-etps-on-lse-25458/)
- [WisdomTree Europe — Short & Leveraged ETP centre (GB)](https://www.wisdomtree.eu/en-gb/resource-library/short-and-leveraged-centre)
- [WisdomTree FTSE 100 1x Daily Short (SUK1)](https://www.wisdomtree.eu/en-gb/etps/equities/wisdomtree-ftse-100-1x-daily-short)
- [WisdomTree FTSE 250 1x Daily Short (1MCS) — Bloomberg](https://www.bloomberg.com/quote/1MCS:LN)
- [WisdomTree Natural Gas 1x Daily Short (SNGA)](https://www.wisdomtree.eu/en-gb/products/short-leveraged-etps/commodities/wisdomtree-natural-gas-1x-daily-short)
- [WisdomTree launches three inverse government bond ETPs — ETF Strategy](https://www.etfstrategy.com/wisdomtree-launches-three-inverse-government-bond-etps-95487/)
- [Xtrackers FTSE 100 Short Daily UCITS ETF (XUKS) — HL](https://www.hl.co.uk/shares/shares-search-results/x/xtrackers-ftse-100-short-daily-ucits)
- [Xtrackers ShortDAX x2 (DBPD)](https://www.investing.com/etfs/db-xtrackers-shortdax-2x-daily)
- [Lyxor double-short ETFs on Treasuries, gilts, JGBs — ETF Strategy](https://www.etfstrategy.com/lyxor-introduces-double-short-etfs-on-treasuries-gilts-and-japanese-government-bonds-72356/)
- [Amundi MSCI USA Daily (-1x) Inverse](https://www.amundietf.co.uk/en/instit/products/equity-etf/lyxor-sp-500-daily-2x-inverse-ucits-etf-acc/lu1327051279/eur)
- [Société Générale launches 74 inverse and leveraged ETPs on LSE — ETF Strategy](https://www.etfstrategy.com/societe-generale-launches-74-inverse-and-leveraged-etps-on-lse-26983/)
- [GraniteShares lists 18 leveraged and inverse US stock ETPs — ETF Stream](https://www.etfstream.com/news/graniteshares-lists-18-leveraged-and-inverse-us-stock-etps)
- [Leverage Shares -3x Short Nvidia (NV3S)](https://finance.yahoo.com/quote/NV3S.L/)

---

*Last updated: 2026-04-18*
