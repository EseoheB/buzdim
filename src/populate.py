"""
populate.py

Loads the BuzDim ontology structure (output/buzdim.owl), adds the 28
ShopLite individuals from the CSV files in data/, and saves the result
as output/buzdim_populated.owl.

It then runs the HermiT reasoner as an early check. At this stage no
rules have been added, so the only expected inferences come from the
two defined classes:
    HighImpactComponent -> orders_db
    OverloadedServer    -> server_d

Design reference: docs/buzdim_model.md (section 6)

Run from the project root, after build_ontology.py:
    python src/populate.py
"""

import csv
from pathlib import Path

from owlready2 import (
    get_ontology,
    AllDifferent,
    sync_reasoner,
    OwlReadyInconsistentOntologyError,
)

# Paths are built from this file's location, so the script works no matter
# which folder it is run from, and spaces in folder names are not a problem.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
STRUCTURE_FILE = OUTPUT_DIR / "buzdim.owl"
POPULATED_FILE = OUTPUT_DIR / "buzdim_populated.owl"

ONTOLOGY_IRI = "http://www.example.org/buzdim.owl#"


def read_csv(filename):
    """Read a CSV file from data/ and return its rows as a list of dictionaries."""
    with open(DATA_DIR / filename, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_entity(onto, name):
    """
    Look up a class or individual by name in the ontology.

    Raises a clear error if the name does not exist, which catches typos
    in the CSV files instead of failing silently later.
    """
    entity = onto[name]
    if entity is None:
        raise ValueError(f"'{name}' was not found in the ontology. Check the CSV files for typos.")
    return entity


def load_structure():
    """Load the empty ontology structure saved by build_ontology.py."""
    # Loading from an open file object avoids path problems on Windows.
    with open(STRUCTURE_FILE, "rb") as f:
        return get_ontology(ONTOLOGY_IRI).load(fileobj=f)


def create_individuals(onto):
    """
    Create every individual from the CSV files.

    Teams and monitoring tools are created first because components
    point to them. Each component, alert, and incident is created as
    a member of the class named in its CSV row.
    """
    for row in read_csv("teams.csv"):
        onto.Team(row["name"])

    for row in read_csv("monitoring_tools.csv"):
        onto.MonitoringTool(row["name"])

    for row in read_csv("components.csv"):
        component_class = get_entity(onto, row["class"])
        component_class(row["name"])

    for row in read_csv("alerts.csv"):
        alert_class = get_entity(onto, row["class"])
        alert_class(row["name"])

    for row in read_csv("incidents.csv"):
        onto.Incident(row["name"])


def add_links(onto):
    """Add the relationships between individuals and the server metric values."""

    # Ownership, hosting, and monitoring. Blank CSV cells are skipped on
    # purpose: infrastructure does not run on a server, and order_queue
    # has no monitoring tool (the incomplete data that CQ7 looks for).
    for row in read_csv("components.csv"):
        component = get_entity(onto, row["name"])

        # ownedBy is functional, so it holds a single value, not a list.
        component.ownedBy = get_entity(onto, row["owned_by"])

        if row["runs_on"]:
            component.runsOn.append(get_entity(onto, row["runs_on"]))

        if row["monitored_by"]:
            component.monitoredBy.append(get_entity(onto, row["monitored_by"]))

    # Only direct dependencies are asserted. The reasoner fills in the
    # transitive dependsOn links and the inverse isDirectlyDependedOnBy.
    for row in read_csv("dependencies.csv"):
        component = get_entity(onto, row["component"])
        dependency = get_entity(onto, row["directly_depends_on"])
        component.directlyDependsOn.append(dependency)

    for row in read_csv("alerts.csv"):
        component = get_entity(onto, row["on_component"])
        component.hasAlert.append(get_entity(onto, row["name"]))

    for row in read_csv("incidents.csv"):
        incident = get_entity(onto, row["name"])
        incident.affects.append(get_entity(onto, row["affects"]))

    # The metric properties are functional, so each holds one float value.
    # float() turns the CSV text "95.0" into the number 95.0, which the
    # OverloadedServer datatype restriction needs.
    for row in read_csv("server_metrics.csv"):
        server = get_entity(onto, row["server"])
        server.cpuUsage = float(row["cpu_usage"])
        server.memoryUsage = float(row["memory_usage"])
        server.diskUsage = float(row["disk_usage"])


def print_checks(onto):
    """Print counts that confirm every individual and link was added."""
    individuals = list(onto.individuals())
    components = list(onto.Component.instances())
    dependency_links = sum(len(c.directlyDependsOn) for c in components)

    print("Individuals:", len(individuals), "(expected 28)")
    print("Components:", len(components), "(expected 14)")
    print("Direct dependency links:", dependency_links, "(expected 12)")
    print("Alerts:", len(list(onto.Alert.instances())), "(expected 4)")
    print("Incidents:", len(list(onto.Incident.instances())), "(expected 4)")


def run_consistency_check(onto):
    """
    Run HermiT to confirm the populated ontology is consistent.

    This runs after saving, so the inferred facts are only used for the
    printout below and are not written into buzdim_populated.owl.
    """
    try:
        with onto:
            sync_reasoner()
    except OwlReadyInconsistentOntologyError:
        print("Consistency check: INCONSISTENT. Check the data for conflicting facts.")
        return

    print("Consistency check: consistent")
    print("HighImpactComponent:", list(onto.HighImpactComponent.instances()), "(expected [buzdim.orders_db])")
    print("OverloadedServer:", list(onto.OverloadedServer.instances()), "(expected [buzdim.server_d])")


def main():
    onto = load_structure()

    with onto:
        create_individuals(onto)
        add_links(onto)
        # Declare every individual distinct. Needed for the CQ4 count and so
        # that a component given two owners is reported as an error instead
        # of the two teams being treated as the same team.
        AllDifferent(list(onto.individuals()))

    print_checks(onto)

    onto.save(file=str(POPULATED_FILE), format="rdfxml")
    print("Saved to output/buzdim_populated.owl")

    run_consistency_check(onto)


if __name__ == "__main__":
    main()
