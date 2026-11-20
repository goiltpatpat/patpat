# Experience First

**Rule:** Work backward from the consumer's interface (CLI, API, errors, output); never leak internal plumbing across the boundary. Errors must state what failed, observed evidence, and concrete remediation.

**Test:** Invoke and test the surface as a consumer—if usage or testing is awkward, fix the boundary before the internals.
