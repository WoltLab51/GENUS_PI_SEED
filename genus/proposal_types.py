"""Shared proposal-type identifiers.

A neutral leaf module (it imports nothing) so policy code can name a RuleProposal
without importing the maturation module that produces it. This is what keeps the
governance / maturation / proposals cluster acyclic: maturation still asks
governance for a decision, but governance no longer reaches back into maturation
just to know a type string.
"""

RULE_PROPOSAL = "RuleProposal"
