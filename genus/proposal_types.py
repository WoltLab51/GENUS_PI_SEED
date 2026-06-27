"""Shared type identifiers.

A neutral leaf module (it imports nothing) so policy and reactor code can name a
proposal or rule type without importing the module that produces it. This keeps
the governance / maturation / proposals / rules cluster acyclic: governance names
a RuleProposal and the activity reactor reads active expectation rules, neither by
importing maturation.
"""

RULE_PROPOSAL = "RuleProposal"
ACTIVITY_EXPECTATION_RULE = "activity_expectation_v1"
