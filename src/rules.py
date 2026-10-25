"""
rules.py

Adds the five SWRL production rules to the populated BuzDim ontology,
runs the HermiT reasoner, and prints what the rules inferred.

Steps:
    1. Load output/buzdim_populated.owl
    2. Add SWRL rules 1 to 4, 6, and 7 (rule 5 is the OverloadedServer
       defined class, built in build_ontology.py)
    3. Save the ontology with rules as output/buzdim_rules.owl, before
       reasoning, so the file holds only asserted facts and rules
    4. Run HermiT with property inference turned on (needed for rule 6)
    5. Assign MinorIncident in Python to incidents not classified as
       critical (a closed-world decision, see assign_minor_incidents)
    6. Print every result next to its expected answer

Design reference: docs/buzdim_model.md (section 5)

Run from the project root, after populate.py:
    python src/rules.py
"""

from pathlib import Path

from owlready2 import (
    get_ontology,
    Imp,
    sync_reasoner,
    OwlReadyInconsistentOntologyError,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
POPULATED_FILE = OUTPUT_DIR / "buzdim_populated.owl"
RULES_FILE = OUTPUT_DIR / "buzdim_rules.owl"

ONTOLOGY_IRI = "http://www.example.org/buzdim.owl#"

# The SWRL rules, in owlready2 syntax. owlready2 separates atoms with
# commas; Protege shows the same rules with ^ between atoms.
RULES = [
    (
        "Rule 1: a component with a critical alert is failed",
        "Component(?c), hasAlert(?c, ?a), CriticalAlert(?a) -> FailedComponent(?c)",
    ),
    (
        "Rule 2: a service that depends on a failed component is affected",
        "Service(?s), dependsOn(?s, ?c), FailedComponent(?c) -> AffectedService(?s)",
    ),
    (
        "Rule 3: a service running on a failed server is affected",
        "Service(?s), runsOn(?s, ?v), Server(?v), FailedComponent(?v) -> AffectedService(?s)",
    ),
    (
        "Rule 4: an incident affecting a customer-facing service is critical",
        "Incident(?i), affects(?i, ?s), CustomerFacingService(?s) -> CriticalIncident(?i)",
    ),
    (
        "Rule 6: an incident notifies the team that owns the affected component",
        "Incident(?i), affects(?i, ?c), ownedBy(?c, ?t) -> shouldNotify(?i, ?t)",
    ),
    # Rule 7 was added after testing. HermiT applied rule 2 only to direct
    # dependencies: it does not pass links it derives from the transitive
    # dependsOn property into SWRL rules, so web_frontend was missed.
    # This rule spreads impact one step at a time instead, which models how
    # failures cascade through real systems.
    (
        "Rule 7: a service that depends on an affected service is also affected",
        "Service(?s), dependsOn(?s, ?x), AffectedService(?x) -> AffectedService(?s)",
    ),
]


def load_populated():
    """Load the populated ontology saved by populate.py."""
    with open(POPULATED_FILE, "rb") as f:
        return get_ontology(ONTOLOGY_IRI).load(fileobj=f)


def add_rules(onto):
    """Add each SWRL rule to the ontology and print it."""
    print("=== SWRL rules added ===")
    with onto:
        for label, rule_text in RULES:
            rule = Imp()
            rule.set_as_rule(rule_text)
            print(label)
            print("   ", rule_text)
    print()


def names(entities):
    """Return the sorted names of a group of individuals, for clean printing."""
    return sorted(e.name for e in entities)


def assign_minor_incidents(onto):
    """
    Mark every incident that is not critical as a MinorIncident.

    This is done in Python rather than by the reasoner on purpose. OWL uses
    the open world assumption: the reasoner never concludes that an incident
    is minor just because nothing proved it critical, since a missing fact
    only means "unknown". Treating "not proven critical" as "minor" is a
    closed-world decision made by the application, after reasoning.
    """
    with onto:
        for incident in onto.Incident.instances():
            if not isinstance(incident, onto.CriticalIncident):
                incident.is_a.append(onto.MinorIncident)


def print_results(onto):
    """Print each inferred result next to the expected answer from the design file."""
    print("=== Results after reasoning ===")

    print("FailedComponent (rule 1):", names(onto.FailedComponent.instances()))
    print("    expected: ['orders_db']")

    print("AffectedService (rules 2, 3, and 7):", names(onto.AffectedService.instances()))
    print("    expected: ['checkout_service', 'inventory_service', 'payment_service', 'web_frontend']")
    print("    note: rule 3 adds nothing in the main run, since no server has failed")

    # INDIRECT_dependsOn is worked out by owlready2 in Python, through the
    # subproperty and transitivity. It shows the chain exists, even though
    # HermiT does not pass the transitive link to rule 2. Rule 7 reaches
    # web_frontend instead, through checkout_service.
    print("web_frontend dependsOn (direct and indirect):", names(onto.web_frontend.INDIRECT_dependsOn))
    print("    web_frontend is affected by rule 7, because checkout_service is affected")

    print("CriticalIncident (rule 4):", names(onto.CriticalIncident.instances()))
    print("    expected: ['inc_001', 'inc_004']")

    print("MinorIncident (Python step):", names(onto.MinorIncident.instances()))
    print("    expected: ['inc_002', 'inc_003']")

    print("shouldNotify (rule 6):")
    for incident in sorted(onto.Incident.instances(), key=lambda i: i.name):
        print("   ", incident.name, "->", names(incident.shouldNotify))
    print("    expected: inc_001 and inc_004 -> storefront_team, "
          "inc_002 -> payments_team, inc_003 -> platform_team")

    print("HighImpactComponent (defined class):", names(onto.HighImpactComponent.instances()))
    print("    expected: ['orders_db']")
    print("OverloadedServer (defined class, rule 5):", names(onto.OverloadedServer.instances()))
    print("    expected: ['server_d']")


def main():
    onto = load_populated()
    add_rules(onto)

    # Save before reasoning, so this file holds the asserted facts and the
    # rules only. It can be opened in Protege to view and rerun the rules.
    onto.save(file=str(RULES_FILE), format="rdfxml")
    print("Saved to output/buzdim_rules.owl")
    print()

    # infer_property_values=True is needed for rule 6, which creates new
    # shouldNotify links rather than new class memberships.
    try:
        with onto:
            sync_reasoner(infer_property_values=True)
    except OwlReadyInconsistentOntologyError:
        print("The ontology is INCONSISTENT after adding the rules. Check the rules and data.")
        return
    print()
    print("Consistency check: consistent")
    print()

    assign_minor_incidents(onto)
    print_results(onto)


if __name__ == "__main__":
    main()
