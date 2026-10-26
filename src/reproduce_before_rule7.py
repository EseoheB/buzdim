"""
reproduce_before_rule7.py

Reproduces the HermiT limitation described in the report. It runs the SWRL
rules WITHOUT rule 7 and shows that web_frontend is not inferred as an
AffectedService, even though it depends on the failed orders_db through
checkout_service.

The reason: HermiT applies rule 2 to direct dependencies, but it does not pass
the dependsOn links it derives from transitivity into SWRL rules. Rule 7
(a service that depends on an affected service is also affected) was added
to fix this. Running rules.py afterwards shows the result with all rules.

This script does not save any ontology file, so it cannot change the main
results.

Run from the project root, after populate.py:
    python src/reproduce_before_rule7.py
"""

from owlready2 import sync_reasoner

import rules  # reuses the rule list, loading, and printing helpers

EXPECTED_WITH_ALL_RULES = ["checkout_service", "inventory_service", "payment_service", "web_frontend"]


def main():
    onto = rules.load_populated()

    # Use every rule except rule 7, as in the first version of the system.
    rules.RULES = [rule for rule in rules.RULES if not rule[0].startswith("Rule 7")]
    print("Running the SWRL rules WITHOUT rule 7 (the first version of the system)")
    print()
    rules.add_rules(onto)

    with onto:
        sync_reasoner(infer_property_values=True)
    print()

    affected = rules.names(onto.AffectedService.instances())
    missing = sorted(set(EXPECTED_WITH_ALL_RULES) - set(affected))

    print("=== Results without rule 7 ===")
    print("FailedComponent (rule 1):", rules.names(onto.FailedComponent.instances()))
    print("AffectedService (rules 2 and 3 only):", affected)
    print("    expected with all rules:", EXPECTED_WITH_ALL_RULES)
    print("Missing from AffectedService:", missing)
    print()

    # owlready2 works out the full dependency chain in Python, which shows the
    # link HermiT did not pass to rule 2 really exists.
    print("web_frontend dependsOn (direct and indirect, worked out by owlready2):",
          rules.names(onto.web_frontend.INDIRECT_dependsOn))
    print("    orders_db is in this list, through checkout_service, so rule 2 should apply")
    print("    to web_frontend. HermiT applied rule 2 only to direct dependencies and did")
    print("    not pass this transitive link to the SWRL rules.")
    print()
    print("Rule 7 fixes this by spreading impact one step at a time: run rules.py to see")
    print("web_frontend added once checkout_service is affected.")


if __name__ == "__main__":
    main()
