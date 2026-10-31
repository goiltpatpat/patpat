# Prototype Playbook

Read [repository truth](../principles/repository-truth.md), [smallest safe change](../principles/smallest-safe-change.md), [proof over proxy](../principles/proof-over-proxy.md), and [attack the premise](../principles/attack-the-premise.md).

## Structured Spiking Protocol

Use structured spiking to settle an empirical fork, test an API constraint, or evaluate performance tradeoffs before committing to a production contract.

1. **Explicit Hypothesis**: State the exact question, the competing approaches, and the observable threshold or metric that will decide between them.
2. **Disposable Harness**: Create the spike harness strictly in an isolated scratch area (e.g. `<scratch>/spike/` or a temporary branch) outside tracked production source trees.
3. **Controlled Telemetry**: Keep inputs, loads, and environmental conditions identical across competing variants. Capture concrete runtime telemetry (latency, memory, error signatures, or ergonomics).
4. **Falsifiable Evaluation**: Compare observed evidence directly against the hypothesis threshold. If an approach fails its premise, reject it cleanly.
5. **Clean Teardown**: Tear down all disposable spike artifacts immediately unless the user explicitly requests their preservation.
6. **Production Handoff**: Never promote prototype scratch code directly to production. Once the design fork is settled, discard the spike and hand the verified specification to `patpat-change` or `patpat-architect` for repository-native implementation.
