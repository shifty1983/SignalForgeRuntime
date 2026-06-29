# Source Model Migration Plan

The clean repo now has two purposes:

1. Preserve and replay the locked V3.2.2 artifact sequence.
2. Migrate the engines that originally created those artifacts.

## Existing bootstrap layer

The runtime bootstraps are not the full trading system by themselves. They are the artifact replay and parity layer.

They answer:

- Can the clean repo read the locked artifacts?
- Can it sequence the known backtest artifacts?
- Can it validate V3.2.2 paper-candidate readiness from the artifact outputs?

## Required engine layers

The clean repo must also contain backtesting engines and underlying decision engines.

## Backtesting engines

These recreate historical artifacts from historical inputs.

Target location:

src/signalforge/backtesting/

Examples:

- historical decision row builder
- historical strategy candidate builder
- historical strategy selection row builder
- walk-forward expectancy builder
- quote join and quote attribution builders
- position sizing replay
- portfolio allocator replay
- equity reconstruction
- robustness and stress validation

## Underlying decision engines

These are reusable engines used by both backtesting and paper trading.

Target location:

src/signalforge/engines/

Examples:

- regime classification
- asset behavior classification
- option behavior classification
- strategy family eligibility
- expected value and expectancy scoring
- strategy selection
- leg construction
- portfolio allocation
- spread guardrail
- prior symbol/regime gate
- order intent generation

## Legacy source snapshot

The legacy source snapshot is stored at:

legacy/source_snapshots/v3_2_2/

It is intentionally not imported by production runtime code.

It exists so we can migrate with traceability:

legacy source -> clean engine -> parity test against locked artifact

## Migration order

1. Historical decision rows
2. Historical strategy candidate rows
3. Walk-forward expectancy
4. Historical strategy selection rows
5. Strategy family eligibility
6. Leg selection and contract construction
7. Position sizing replay
8. Portfolio selected trade sequence
9. Portfolio allocator v2
10. Quote join and attribution
11. V3.2.2 prune, stress, and ruleset lock
12. Paper order intent and broker translation

## Rule

Bootstraps stay as parity fixtures.

Migrated engines become the paper-trading and backtesting source of truth.
