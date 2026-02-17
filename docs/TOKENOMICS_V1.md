# RamIA Tokenomics v1 Specification

## Scope
This specification defines Tokenomics v1 for the RamIA chain with a fixed max supply and deterministic emission behavior suitable for local-first nodes.

## 1) Fixed Supply
- **Token symbol:** RAMIA
- **Total fixed supply:** **100,000,000 RAMIA**
- Supply is hard-capped and must never be exceeded by all minted allocations combined.

## 2) Allocation Table
| Allocation Bucket | Percent | Amount (RAMIA) |
|---|---:|---:|
| Community | 45% | 45,000,000 |
| Team | 15% | 15,000,000 |
| Treasury | 15% | 15,000,000 |
| Founder | 10% | 10,000,000 |
| Market Incentives | 10% | 10,000,000 |
| Liquidity | 5% | 5,000,000 |
| **Total** | **100%** | **100,000,000** |

## 3) Vesting Rules
Vesting uses second-based timestamps (`start_ts`, `now_ts`) and integer unlock amounts.

- **Community:** Emission-based (no cliff), controlled by block reward schedule below.
- **Market Incentives:** Emission-based (no cliff), controlled by block reward schedule below.
- **Team:** 12-month cliff, then 48-month linear vesting.
- **Treasury:** 12-month cliff, then 36-month linear vesting.
- **Founder:** 12-month cliff, then 48-month linear vesting.
- **Liquidity:** Immediate at TGE (or governance-managed deployment), no vesting lock by default.

`vesting_unlock(...)` in `tokenomics_v1.py` defines the canonical unlock math.

## 4) Emission Engine (Community + Market Pools)
Emission budget for block rewards is constrained to:

- **Community + Market Incentives = 55,000,000 RAMIA** maximum mintable via emission.

Block reward logic:
1. Compute baseline reward as `remaining_pool / epochs_remaining` (integer floor, minimum 1 if pool remains).
2. Compute AI multiplier from state metrics.
3. Clamp AI multiplier to `[0.5, 1.5]`.
4. Reward = `floor(baseline * multiplier)`.
5. Reward must be clamped to `remaining_pool` so emission cannot exceed budget.

## 5) Epoch Definition & On-Chain Tracking
- **Epoch length:** `86,400 seconds` (24h).
- Epoch index is derived from wall-clock timestamp and persisted state.
- Remaining emission pool is tracked in `token_state.json` under node `datadir`.

Canonical tracked keys:
- `emission_pool_total` (55,000,000)
- `remaining_pool`
- `minted_total`
- `epoch_length_sec` (86,400)
- `genesis_ts`
- `last_emission_ts`
- `last_reward`

`ramia_core_v1.py` updates this state after accepted mined blocks and writes deterministic JSON.

## 6) Safety Invariants
- `minted_total <= emission_pool_total`
- `remaining_pool = emission_pool_total - minted_total`
- Per-block reward is never negative.
- Per-block reward never exceeds `remaining_pool`.
- Total minting across all allocation buckets must not exceed 100,000,000 RAMIA.

## 7) Environment & Deployment Notes
- Local node runs on Termux/PC/Mac/Windows.
- Netlify hosts static PWA and Stripe functions only.
- Stripe card handling is delegated fully to hosted Checkout Sessions.
