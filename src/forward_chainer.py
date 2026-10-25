"""
forward_chainer.py

A data-driven (forward chaining) rule engine for BuzDim, written in Python.

The OWL reasoner reports WHAT is true but not WHY. This engine starts from
the asserted facts, applies the seven production rules in rounds, and prints
every rule firing with the facts that triggered it. It stops when a round
adds nothing new (a fixpoint).

Each round only uses facts known at the start of that round, so the round
number shows how many inference steps a conclusion needed.

Two runs are made:
    Scenario A: the main data from data/ (expected answers in the design file)
    Scenario B: the main data plus a critical alert on server_a, which shows
                rule 3 firing (no server fails in the main data)

Scenario B works on a copy of the facts, so the ontology file is unchanged.

Design reference: docs/buzdim_model.md (sections 5 and 8)

Run from the project root, after populate.py:
    python src/forward_chainer.py
"""

from collections import defaultdict
from pathlib import Path

from owlready2 import get_ontology, Thing, ThingClass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POPULATED_FILE = PROJECT_ROOT / "output" / "buzdim_populated.owl"
ONTOLOGY_IRI = "http://www.example.org/buzdim.owl#"

OBJECT_PROPERTIES = ["directlyDependsOn", "runsOn", "hasAlert", "affects", "ownedBy", "monitoredBy"]
DATA_PROPERTIES = ["cpuUsage", "memoryUsage", "diskUsage"]
CPU_THRESHOLD = 90.0


# ==============================================================
# KNOWLEDGE BASE
# ==============================================================

class KnowledgeBase:
    """
    Holds the facts the rules work on.

    types:     individual name -> set of class names (including superclasses)
    relations: set of (property, subject, object) triples
    values:    (property, subject) -> number, for the server metrics
    """

    def __init__(self):
        self.types = defaultdict(set)
        self.relations = set()
        self.values = {}

    def copy(self):
        """Return an independent copy, so a scenario can change facts safely."""
        new_kb = KnowledgeBase()
        for individual, classes in self.types.items():
            new_kb.types[individual] = set(classes)
        new_kb.relations = set(self.relations)
        new_kb.values = dict(self.values)
        return new_kb

    def is_a(self, individual, class_name):
        """True if the individual belongs to the class."""
        return class_name in self.types.get(individual, set())

    def instances(self, class_name):
        """All individuals in a class, sorted so the trace is the same every run."""
        return sorted(i for i, classes in self.types.items() if class_name in classes)

    def objects(self, prop, subject):
        """All objects linked to the subject by the property, sorted."""
        return sorted(o for (p, s, o) in self.relations if p == prop and s == subject)

    def value(self, prop, subject):
        """The value of a data property, or None if it is missing."""
        return self.values.get((prop, subject))

    def has(self, fact):
        """True if a fact produced by a rule is already known."""
        if fact[0] == "type":
            return self.is_a(fact[1], fact[2])
        return (fact[1], fact[2], fact[3]) in self.relations

    def add(self, fact):
        """Add a fact produced by a rule."""
        if fact[0] == "type":
            self.types[fact[1]].add(fact[2])
        else:
            self.relations.add((fact[1], fact[2], fact[3]))

    def count(self):
        """Return the number of class memberships, relations, and values."""
        memberships = sum(len(c) for c in self.types.values())
        return memberships, len(self.relations), len(self.values)


def load_knowledge_base():
    """
    Read the asserted facts from output/buzdim_populated.owl.

    No reasoner is run here: the point is to show the rules doing the work.
    Each individual's classes include all superclasses, so orders_db counts
    as a Database, a DataStore, and a Component.
    """
    with open(POPULATED_FILE, "rb") as f:
        onto = get_ontology(ONTOLOGY_IRI).load(fileobj=f)

    kb = KnowledgeBase()

    for individual in onto.individuals():
        for cls in individual.is_a:
            if isinstance(cls, ThingClass):
                for ancestor in cls.ancestors():
                    if ancestor is not Thing:
                        kb.types[individual.name].add(ancestor.name)

    for prop_name in OBJECT_PROPERTIES:
        for subject, obj in onto[prop_name].get_relations():
            kb.relations.add((prop_name, subject.name, obj.name))

    for prop_name in DATA_PROPERTIES:
        for subject, value in onto[prop_name].get_relations():
            kb.values[(prop_name, subject.name)] = float(value)

    return kb


def apply_subproperty_axiom(kb):
    """
    Copy every directlyDependsOn link to dependsOn (the subproperty axiom).

    Transitivity is deliberately NOT applied here. This matches what the
    HermiT reasoner passed to the SWRL rules, so both systems reach their
    conclusions by the same route: indirect impact comes from rule 7.
    """
    direct_links = [(s, o) for (p, s, o) in kb.relations if p == "directlyDependsOn"]
    for subject, obj in direct_links:
        kb.relations.add(("dependsOn", subject, obj))
    return len(direct_links)


# ==============================================================
# PRODUCTION RULES
# Each rule checks the knowledge base and yields
# (new fact, reason) pairs. A fact is either
# ("type", individual, class) or ("rel", property, subject, object).
# ==============================================================

def rule_1(kb):
    """A component with a critical alert is failed."""
    for c in kb.instances("Component"):
        for a in kb.objects("hasAlert", c):
            if kb.is_a(a, "CriticalAlert"):
                yield ("type", c, "FailedComponent"), f"{c} has critical alert {a}"


def rule_2(kb):
    """A service that depends on a failed component is affected."""
    for s in kb.instances("Service"):
        for c in kb.objects("dependsOn", s):
            if kb.is_a(c, "FailedComponent"):
                yield ("type", s, "AffectedService"), f"{s} depends on failed component {c}"


def rule_3(kb):
    """A service running on a failed server is affected."""
    for s in kb.instances("Service"):
        for v in kb.objects("runsOn", s):
            if kb.is_a(v, "Server") and kb.is_a(v, "FailedComponent"):
                yield ("type", s, "AffectedService"), f"{s} runs on failed server {v}"


def rule_4(kb):
    """An incident affecting a customer-facing service is critical."""
    for i in kb.instances("Incident"):
        for s in kb.objects("affects", i):
            if kb.is_a(s, "CustomerFacingService"):
                yield ("type", i, "CriticalIncident"), f"{i} affects customer-facing service {s}"


def rule_5(kb):
    """A server with CPU usage above 90.0 is overloaded."""
    for s in kb.instances("Server"):
        cpu = kb.value("cpuUsage", s)
        if cpu is not None and cpu > CPU_THRESHOLD:
            yield ("type", s, "OverloadedServer"), f"{s} has CPU usage {cpu}, above {CPU_THRESHOLD}"


def rule_6(kb):
    """An incident notifies the team that owns the affected component."""
    for i in kb.instances("Incident"):
        for c in kb.objects("affects", i):
            for t in kb.objects("ownedBy", c):
                yield ("rel", "shouldNotify", i, t), f"{i} affects {c}, which is owned by {t}"


def rule_7(kb):
    """A service that depends on an affected service is also affected."""
    for s in kb.instances("Service"):
        for x in kb.objects("dependsOn", s):
            if kb.is_a(x, "AffectedService"):
                yield ("type", s, "AffectedService"), f"{s} depends on affected service {x}"


RULES = [
    ("Rule 1", rule_1),
    ("Rule 2", rule_2),
    ("Rule 3", rule_3),
    ("Rule 4", rule_4),
    ("Rule 5", rule_5),
    ("Rule 6", rule_6),
    ("Rule 7", rule_7),
]


# ==============================================================
# ENGINE
# ==============================================================

def format_fact(fact):
    """Turn a fact tuple into readable text, such as FailedComponent(orders_db)."""
    if fact[0] == "type":
        return f"{fact[2]}({fact[1]})"
    return f"{fact[1]}({fact[2]}, {fact[3]})"


def forward_chain(kb):
    """
    Apply all rules in rounds until no new facts appear.

    In each round, every rule is checked against the facts known at the
    start of the round. New facts are added only after the round ends,
    so a conclusion that needs another conclusion appears a round later.
    """
    round_number = 0
    while True:
        round_number += 1
        new_facts = {}  # fact -> (rule label, reason); keeps the first reason found

        for label, rule in RULES:
            for fact, reason in rule(kb):
                if not kb.has(fact) and fact not in new_facts:
                    new_facts[fact] = (label, reason)

        print(f"Round {round_number}")
        if not new_facts:
            print(f"  No new facts. Fixpoint reached after {round_number - 1} rounds.")
            return

        for fact, (label, reason) in new_facts.items():
            print(f"  {label} fired: {reason}")
            print(f"          => {format_fact(fact)}")

        for fact in new_facts:
            kb.add(fact)


def assign_minor_incidents(kb):
    """
    Closed-world step after chaining: any incident not proven critical is minor.

    This is an application decision, not a logical conclusion. Under the
    open world assumption, "not proven critical" only means "unknown".
    """
    print("Closed-world step (after chaining)")
    for i in kb.instances("Incident"):
        if not kb.is_a(i, "CriticalIncident"):
            kb.add(("type", i, "MinorIncident"))
            print(f"  {i} was not proven critical => MinorIncident({i})")


def print_summary(kb, expected):
    """Print the final members of each inferred class next to the expected answer."""
    print("Summary")
    for class_name, expected_members in expected.items():
        print(f"  {class_name}: {kb.instances(class_name)}")
        print(f"      expected: {expected_members}")


def run_scenario(title, kb, expected):
    """Run forward chaining on a knowledge base and print the full trace."""
    print("=" * 70)
    print(title)
    print("=" * 70)
    memberships, relations, values = kb.count()
    print(f"Starting facts: {memberships} class memberships, {relations} relations, {values} metric values")
    links = apply_subproperty_axiom(kb)
    print(f"Subproperty axiom: {links} directlyDependsOn links also count as dependsOn")
    print()
    forward_chain(kb)
    print()
    assign_minor_incidents(kb)
    print()
    print_summary(kb, expected)
    print()


def main():
    base_kb = load_knowledge_base()

    # --- Scenario A: main data ---
    kb_a = base_kb.copy()
    run_scenario(
        "Scenario A: main data",
        kb_a,
        {
            "FailedComponent": ["orders_db"],
            "AffectedService": ["checkout_service", "inventory_service", "payment_service", "web_frontend"],
            "CriticalIncident": ["inc_001", "inc_004"],
            "MinorIncident": ["inc_002", "inc_003"],
            "OverloadedServer": ["server_d"],
        },
    )
    print("Notifications (rule 6):")
    for i in kb_a.instances("Incident"):
        print(f"  {i} -> {kb_a.objects('shouldNotify', i)}")
    print()

    # --- Scenario B: a critical alert arrives on server_a ---
    kb_b = base_kb.copy()
    kb_b.types["alert_005"].update({"Alert", "CriticalAlert"})
    kb_b.relations.add(("hasAlert", "server_a", "alert_005"))
    print("New data for scenario B: hasAlert(server_a, alert_005), CriticalAlert(alert_005)")
    print()
    run_scenario(
        "Scenario B: critical alert on server_a (rule 3 demo)",
        kb_b,
        {
            "FailedComponent": ["orders_db", "server_a"],
            "AffectedService": [
                "checkout_service", "inventory_service", "payment_service",
                "search_service", "web_frontend",
            ],
        },
    )
    newly_affected = sorted(set(kb_b.instances("AffectedService")) - set(kb_a.instances("AffectedService")))
    print(f"Newly affected compared with scenario A: {newly_affected}")
    print("    expected: ['search_service']")


if __name__ == "__main__":
    main()
