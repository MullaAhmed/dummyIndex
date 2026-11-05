# Scoped maintenance

Resume feature maintenance and record explicit drift acknowledgements.

`dummyindex/cli/maintain.py` plans, starts, advances and resumes the persisted maintenance units supplied by `dummyindex/context/domains/fleet.py`. Completing a unit and advancing the index anchor are separate operations.

`dummyindex/context/domains/drift_acks.py` stores per-feature acknowledgements of the current source fingerprint in a local cache. Acknowledgement does not rewrite source or establish that changed behavior was tested. Changed fingerprints invalidate previous acknowledgement.

The Stop gate attributes maintenance to the source paths changed in the current session; unrelated drift remains a separate backlog. See `dummyindex/context/reconcile_gate.py`.
