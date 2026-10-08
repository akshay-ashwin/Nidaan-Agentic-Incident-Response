"""Evaluation-only ground truth. Must never be imported by agent-accessible code
(nidaan/, settlesim/, baselines/); tests/test_eval.py enforces this.

Development fault types only. A fault missing from this map makes root-cause accuracy
not applicable (None) for a run; nothing else is inferred.
"""

TRUTH_COMPONENT = {"F1": "bank", "F2": "bank", "F4": "ledger", "F6": "worker", "F7": "bank"}
