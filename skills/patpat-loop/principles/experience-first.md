# Experience First

Work backward from the operator or consumer experience to the implementation, not forward from internal technical convenience.

1. Shape the external interface—CLI syntax, API contract, error feedback, and output format—around what the consumer needs to understand and act upon effortlessly.
2. Never leak internal plumbing, temporary tokens, or accidental implementation artifacts across the user boundary.
3. Error messages must be actionable: state what failed, cite the observed evidence, and indicate the concrete remediation.
4. If a feature is awkward or painful to invoke or test, the architecture is wrong.
