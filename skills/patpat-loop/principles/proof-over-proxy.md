# Proof Over Proxy

Define the claim before choosing a check.

- Identify the authoritative artifact or user surface.
- Capture a baseline or reproduce the symptom when relevant.
- Run the smallest targeted automated check.
- Exercise the real behavior when practical.
- Observe the result and material side effects directly.
- Record the action, result, and limitation.

Classify the oracle as repository, runtime, independent reference, or lockstep. Claims of runtime equivalence require an independent reference or lockstep comparison; a build, local implementation, or same-context reviewer cannot prove equivalence.

Bind durable evidence to the exact revision or snapshot it checked, the relevant inputs and environment, and the oracle used. A material change to any binding makes the evidence stale; recollect it instead of carrying a green result forward.

Do not treat compilation, test success, file timestamps, cached output, or an agent summary as proof of a different claim.
