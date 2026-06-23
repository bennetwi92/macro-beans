# Universe verification — ISA + SIPP optimiser

*Compiled 2026-06 from issuer factsheets / justETF / Trading 212 help centre.
Verify any ISIN before relying on it; "young" funds are spliced onto longer-history
proxies for covariance (see `config/universe.toml` `[proxy.*]`).*

## Verified instruments (GBP LSE UCITS lines)

| Key | Fund | GBP ticker | ISIN | TER | Class | Note |
|-----|------|-----------|------|-----|-------|------|
| AVWC | Avantis Global Equity | **AVCG.L** | IE000RJECXS5 | 0.22% | Acc | **Brief said AVWC — that's the EUR Xetra line.** GBP LSE = AVCG. Inception 2024-09. |
| AVSG | Avantis Global Small Cap Value | AVSG.L | IE0003R87OG3 | 0.39% | Acc | OK. |
| XDEW | Xtrackers S&P 500 Equal Weight | XDEW.L | IE00BLNMYC90 | 0.15% | Acc | HL sometimes shows "XDWE"; XDEW canonical. |
| EMIM | iShares Core MSCI EM IMI | EMIM.L | IE00BKM4GZ66 | 0.18% | Acc | EMIM = GBp line, EIMI = USD line. |
| IWQU | iShares Edge MSCI World Quality | IWQU.L | IE00BP3QZ601 | 0.25% | Acc | TER 0.25% (brief said 0.30). "Advanced" version (IE000U1MQKJ2) is a different fund. |
| MVOL | iShares Edge MSCI World Min Vol | MVOL.L | IE00B8FHGS14 | 0.30% | Acc | **Confirmed MVOL, not MINV.** |
| JMFP | JPM Managed Futures (GBP-H) | JMFP.L | IE00BF2SYT35 | 0.57% | Acc | **Confirmed UCITS ETF, not an ETN.** |
| SGLN | iShares Physical Gold | SGLN.L | IE00B4ND3602 | 0.12% | ETC | Physically-backed gold **ETC** (debt security), not a UCITS fund. |
| IGLS | iShares UK Gilts 0–5yr | IGLS.L | IE00B4WXJK79 | 0.07% | **Dist only** | No Acc class. Harmless in a wrapper. |
| ERNS | iShares £ Ultrashort Bond | ERNS.L | **IE00BCRY6441** | 0.09% | **Dist only** | **Brief ISIN IE00BCRY6557 = EUR (ERNE) line.** Corrected. |
| DFND_EU | HANetf Future of European Defence (Screened, ex-US) | **NAVY.L** | IE000I7E6HL0 | 0.39% | Acc | **GBP line = NAVY** (ARMY = USD, 8RMY = EUR). Launched 2025-04. |
| URNM | Sprott Uranium Miners | **URNP.L** | IE0005YK6564 | 0.85% | Acc | GBP line = URNP (URNM = USD). Launched 2022-05. |
| GLIN | iShares Global Infrastructure | **INFR.L** | IE00B1FZS467 | 0.65% | **Dist only** | No GBP Acc line (Acc = USD CBUX). Harmless in a wrapper. |

Other brief tickers (not in the working universe): VWRP IE00BK5BQT80 0.19% Acc (used as
the benchmark, via proxy ACWI); VHVG IE00BK5BQV03 0.12% Acc; DPGT IE000S67ID55 0.44% Acc
(launched 2025-11, viable alt to AVSG); DFNG IE000YYE6WK5 0.55% Acc (the US-tech-heavy
defence line we deliberately avoid).

## Trading 212 SIPP eligibility (as of 2026-06)

- **Operator fee — GONE (confirmed).** T212 took its own FCA SIPP authorisation in
  Feb 2026; no platform/dealing/custody/admin/exit fees. Only charge is the 0.15% FX
  fee on non-GBP purchases. The old ~£75–100 Gaudi figure is stale. → `fixed_fee_gbp = 0`.
- **SGLN (gold ETC) — LIKELY eligible, not explicitly documented.** T212's SIPP options
  page excludes "ETNs and other products outside our SIPP risk appetite" — names **ETNs
  only, not ETCs** — and SGLN is tradable on-platform. Treat as a strong indication, not a
  guarantee; confirm by searching SGLN inside the SIPP wrapper.
- **JMFP (managed futures) — UNCONFIRMED.** It clears the ETN exclusion (it's a UCITS
  ETF) but a derivatives-based strategy is exactly what the "risk appetite" catch-all
  could exclude. Verify instrument-by-instrument before relying on it.

### Same-role fallbacks if a SIPP holding is blocked
- **Gold (SGLN blocked):** other physical gold ETCs (SGLP, IGLN) share the ETC structure
  so don't help. A true equity fallback is a **gold-miners UCITS ETF** (VanEck Gold Miners,
  GDX/IE00BQQP9F84) — higher beta, equity-correlated, not spot gold.
- **Managed futures (JMFP blocked):** no clean SIPP-eligible listed trend ETF confirmed
  (US DBMF/iMGP aren't UCITS). Partial diversifier = a broad-commodity UCITS ETF, accepting
  it lacks the short/trend (crisis-alpha) capability.

To switch: edit the holding's `ticker`/`proxy` in `config/universe.toml` (or drop it from
`[sipp].universe` in `config/constraints.toml`) and re-run. The optimiser re-solves around
whatever universe it is given.
