"""
queries.py

Answers the BuzDim competency questions in one place:

    CQ1   Which monitoring tool watches each server?        (SPARQL lookup)
    CQ2   Which services are affected if orders_db fails?   (SWRL rules + reasoner)
    CQ3   Root cause of the checkout_service outage         (see backward_chainer.py)
    CQ4   Which components are depended on by 3+ services?  (defined class)
    CQ5   Which incidents are critical and which minor?     (rule 4 + Python step)
    CQ6  How are servers classified by CPU usage?          (defined class, live demo)
    CQ7  Which components have no monitoring data?         (Python, closed world)
    CQ8  What happens with conflicting health data?        (consistency test)

The main questions use output/buzdim_rules.owl, which holds the asserted
facts and the SWRL rules. The CQ6 live demo and the CQ8 conflict test each
load their own separate copy in a new owlready2 World, so changes made
there can never affect the main answers.

Design reference: docs/buzdim_model.md (sections 7 and 8)

Run from the project root, after rules.py:
    python src/queries.py
"""

from pathlib import Path

from owlready2 import (
    World,
    default_world,
    get_ontology,
    sync_reasoner,
    OwlReadyInconsistentOntologyError,
)

import rules  # reuses names() and assign_minor_incidents() from rules.py

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULES_FILE = PROJECT_ROOT / "output" / "buzdim_rules.owl"
ONTOLOGY_IRI = "http://www.example.org/buzdim.owl#"

names = rules.names


def heading(text):
    """Print a section heading so each question is easy to find in the trace."""
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def load_rules_ontology(world=None):
    """
    Load buzdim_rules.owl into the given World, or the default one.

    A separate World is a completely independent copy of the ontology.
    """
    with open(RULES_FILE, "rb") as f:
        if world is None:
            return get_ontology(ONTOLOGY_IRI).load(fileobj=f)
        return world.get_ontology(ONTOLOGY_IRI).load(fileobj=f)


# ==============================================================
# CQ1: simple lookup with SPARQL
# Run before reasoning, since a lookup only needs asserted facts.
# ==============================================================

def answer_q3(onto):
    heading("CQ1: Which monitoring tool watches each server? (simple lookup)")

    query = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX bz: <http://www.example.org/buzdim.owl#>
        SELECT ?server ?tool WHERE {
            ?server rdf:type bz:Server .
            ?server bz:monitoredBy ?tool .
        }
    """
    print("SPARQL query:")
    print(query.rstrip())
    print()

    try:
        rows = sorted((row[0].name, row[1].name) for row in default_world.sparql(query))
        print("SPARQL results:")
        for server, tool in rows:
            print(f"  {server} -> {tool}")
    except Exception as error:
        print(f"SPARQL could not run in this environment: {error}")

    # The same question answered in Python, as a cross-check.
    print("Python cross-check:")
    for server in sorted(onto.Server.instances(), key=lambda s: s.name):
        print(f"  {server.name} -> {names(server.monitoredBy)}")
    print("    expected: server_a, server_b -> cloudwatch; server_c, server_d -> prometheus")


# ==============================================================
# CQ2, CQ4, CQ5, CQ6, CQ7: questions answered after reasoning
# ==============================================================

def answer_q4(onto):
    heading("CQ2: Which services are affected if orders_db fails? (complex reasoning)")
    print("FailedComponent:", names(onto.FailedComponent.instances()))
    affected = list(onto.AffectedService.instances())
    direct = [s for s in affected if onto.orders_db in s.directlyDependsOn]
    indirect = [s for s in affected if s not in direct]
    print("Affected directly (rule 2):", names(direct))
    print("Affected indirectly (rule 7):", names(indirect))
    not_affected = [s for s in onto.Service.instances() if s not in affected]
    print("Not affected:", names(not_affected))
    print("    expected: direct checkout_service, inventory_service, payment_service; "
          "indirect web_frontend; not affected search_service")


def answer_q5():
    heading("CQ3: Root cause of the checkout_service outage (backward chaining)")
    print("Answered by backward_chainer.py, which prints the full proof trace.")
    print("    expected: root cause orders_db")


def answer_q7(onto):
    heading("CQ4: Which components are depended on by 3 or more services? (cardinality)")
    print("HighImpactComponent (reasoner):", names(onto.HighImpactComponent.instances()))
    print("Direct service dependents per component:")
    services = list(onto.Service.instances())
    for component in sorted(onto.Component.instances(), key=lambda c: c.name):
        dependents = [s for s in services if component in s.directlyDependsOn]
        if dependents:
            print(f"  {component.name}: {len(dependents)} {names(dependents)}")
    print("    expected: orders_db only (3); product_db and order_queue have 2 each")


def answer_q8(onto):
    heading("CQ5: Which incidents are critical and which are minor? (classification)")
    print("CriticalIncident (rule 4):", names(onto.CriticalIncident.instances()))
    print("MinorIncident (Python step):", names(onto.MinorIncident.instances()))
    print("Teams to notify (rule 6):")
    for incident in sorted(onto.Incident.instances(), key=lambda i: i.name):
        affected = names(incident.affects)
        print(f"  {incident.name} affects {affected} -> notify {names(incident.shouldNotify)}")
    print("    expected: critical inc_001, inc_004; minor inc_002, inc_003")


def answer_q10(onto):
    heading("CQ6: How are servers classified by CPU usage? (automatic classification)")
    print("Rule: OverloadedServer = Server with cpuUsage > 90.0")
    for server in sorted(onto.Server.instances(), key=lambda s: s.name):
        status = "OverloadedServer" if isinstance(server, onto.OverloadedServer) else "not overloaded"
        print(f"  {server.name}: cpuUsage {server.cpuUsage} -> {status}")
    print("    expected: server_d overloaded; server_c at 88.0 not overloaded")


def answer_q10_live():
    """
    Add two brand-new servers to a separate copy and let the reasoner
    classify them, with no rule or class assigned by hand.
    """
    print()
    print("Live demo: adding two new servers to a separate copy of the ontology")
    world = World()
    onto = load_rules_ontology(world)
    with onto:
        server_e = onto.Server("server_e")
        server_e.cpuUsage = 91.5
        server_f = onto.Server("server_f")
        server_f.cpuUsage = 90.0
    print("  Added server_e (cpuUsage 91.5) and server_f (cpuUsage 90.0), asserted only as Server")

    with onto:
        sync_reasoner(world)

    for server in (server_e, server_f):
        status = "OverloadedServer" if isinstance(server, onto.OverloadedServer) else "not overloaded"
        print(f"  {server.name}: cpuUsage {server.cpuUsage} -> {status}")
    print("    expected: server_e overloaded; server_f not overloaded "
          "(the threshold is strictly greater than 90.0)")


def answer_q11(onto):
    heading("CQ7: Which components have no monitoring data? (incomplete information)")
    unmonitored = [c for c in onto.Component.instances() if not c.monitoredBy]
    print("Components with no monitoredBy link (Python check):", names(unmonitored))
    print("    expected: ['order_queue']")
    print("Why Python and not the reasoner: under the open world assumption, a missing")
    print("monitoredBy link means 'unknown', not 'none'. The reasoner cannot conclude")
    print("that order_queue is unmonitored, because a tool might exist that was never")
    print("recorded. Treating missing data as absent is a closed-world application choice.")


# ==============================================================
# CQ8: conflicting data, on a separate copy
# ==============================================================

def answer_q12():
    heading("CQ8: What happens with conflicting health data? (consistency test)")
    world = World()
    onto = load_rules_ontology(world)

    with onto:
        alert = onto.CriticalAlert("alert_005")
        onto.server_a.hasAlert.append(alert)
        onto.server_a.is_a.append(onto.HealthyComponent)
    print("Conflicting facts added to a separate copy:")
    print("  hasAlert(server_a, alert_005), CriticalAlert(alert_005)  (an alert says critical)")
    print("  HealthyComponent(server_a)                               (a health check says healthy)")
    print("Rule 1 will infer FailedComponent(server_a), and HealthyComponent and")
    print("FailedComponent are declared disjoint.")
    print()

    try:
        with onto:
            sync_reasoner(world)
        print("Result: consistent (UNEXPECTED, the conflict was not detected)")
    except OwlReadyInconsistentOntologyError:
        print("Result: the reasoner reports the ontology as INCONSISTENT.")
        print("server_a cannot be both healthy and failed, so the conflict is detected")
        print("instead of one fact silently overriding the other.")
    print("    expected: inconsistent")
    print("The main ontology is unaffected, because this test used a separate World.")


def main():
    onto = load_rules_ontology()

    answer_q3(onto)

    print()
    print("Running HermiT on the main ontology (asserted facts and SWRL rules)...")
    with onto:
        sync_reasoner(infer_property_values=True)
    rules.assign_minor_incidents(onto)

    answer_q4(onto)
    answer_q5()
    answer_q7(onto)
    answer_q8(onto)
    answer_q10(onto)
    answer_q10_live()
    answer_q11(onto)
    answer_q12()


if __name__ == "__main__":
    main()
