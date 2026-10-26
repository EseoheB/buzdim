"""
build_ontology.py

Builds the structure of the BuzDim ontology for cloud service incident
diagnosis: 24 classes, 9 object properties, 3 data properties, and the
axioms that constrain them (disjointness, defined classes, cardinality).

No individuals are added here. They are loaded in a later step.
The result is saved to output/buzdim.owl, which can be opened in Protege.

Design reference: docs/buzdim_model.md (sections 2 to 4)

Run from the project root:
    python src/build_ontology.py
"""

from owlready2 import *

# Create the ontology. The IRI is a unique name for it,
# so it does not need to be a real website.
onto = get_ontology("http://www.example.org/buzdim.owl#")

with onto:

    # ==========================================================
    # SECTION 1: CLASSES (24 in total)
    # Rule: a parent class is always written before its children.
    # ==========================================================

    # --- Top-level classes (parent: Thing) ---
    class Component(Thing):
        """Any part of the ShopLite infrastructure."""
        pass

    class Alert(Thing):
        """A warning raised by a monitoring tool about a component."""
        pass

    class Incident(Thing):
        """A recorded disruption that affects one or more components."""
        pass

    class Team(Thing):
        """An engineering team responsible for components."""
        pass

    class MonitoringTool(Thing):
        """A tool that collects health data, such as CloudWatch or Prometheus."""
        pass

    # --- Component subclasses (parent: Component) ---
    class Service(Component):
        """A software service that performs application work."""
        pass

    class DataStore(Component):
        """A component that stores data."""
        pass

    class Infrastructure(Component):
        """Hardware or network components that services run on or pass through."""
        pass

    class HealthyComponent(Component):
        """A component reported as healthy. Used only in the conflict test (CQ8)."""
        pass

    class FailedComponent(Component):
        """A component that has failed. Filled in by rule 1."""
        pass

    class HighImpactComponent(Component):
        """A component directly depended on by 3 or more services (defined in Section 5)."""
        pass

    # --- Service subclasses (parent: Service) ---
    class CustomerFacingService(Service):
        """A service customers use directly, such as checkout or search."""
        pass

    class InternalService(Service):
        """A back-end service customers never see directly."""
        pass

    class AffectedService(Service):
        """A service impacted by a failure. Filled in by rules 2 and 3."""
        pass

    # --- DataStore subclasses (parent: DataStore) ---
    class Database(DataStore):
        """A persistent database, such as the orders database."""
        pass

    class Cache(DataStore):
        """A fast, temporary data store, such as a session cache."""
        pass

    # --- Infrastructure subclasses (parent: Infrastructure) ---
    class Server(Infrastructure):
        """A machine that hosts services and data stores."""
        pass

    class LoadBalancer(Infrastructure):
        """Distributes incoming traffic across services."""
        pass

    class MessageQueue(Infrastructure):
        """Passes messages between services asynchronously."""
        pass

    # --- Server subclass (parent: Server) ---
    class OverloadedServer(Server):
        """A server with CPU usage above 90% (defined in Section 5)."""
        pass

    # --- Alert subclasses (parent: Alert) ---
    class CriticalAlert(Alert):
        """A severe alert. Triggers rule 1, which marks the component as failed."""
        pass

    class WarningAlert(Alert):
        """A lower-level alert. Does not mark a component as failed."""
        pass

    # --- Incident subclasses (parent: Incident) ---
    class CriticalIncident(Incident):
        """An incident affecting a customer-facing service. Filled in by rule 4."""
        pass

    class MinorIncident(Incident):
        """An incident not classified as critical. Assigned in Python after reasoning."""
        pass


    # ==========================================================
    # SECTION 2: OBJECT PROPERTIES (9 in total)
    # These link one individual to another.
    # ==========================================================

    # dependsOn is transitive: if A depends on B and B depends on C,
    # the reasoner concludes A depends on C.
    class dependsOn(ObjectProperty, TransitiveProperty):
        """A component relies on another component, directly or indirectly."""
        domain = [Component]
        range = [Component]

    # Inheriting from dependsOn makes this a subproperty, so every direct
    # dependency is also a dependsOn link. Only this property is asserted
    # in the data; the reasoner fills in dependsOn.
    class directlyDependsOn(dependsOn):
        """A component relies on another component with no step in between."""
        domain = [Component]
        range = [Component]

    # The inverse lets the reasoner count how many services depend on a
    # component, which the HighImpactComponent definition needs.
    class isDirectlyDependedOnBy(ObjectProperty):
        """The reverse of directlyDependsOn."""
        domain = [Component]
        range = [Component]
        inverse_property = directlyDependsOn

    # The union domain is needed because both services and data stores
    # run on servers. A domain of Service alone would make the reasoner
    # treat orders_db as a Service, which clashes with disjointness.
    class runsOn(ObjectProperty):
        """A service or data store is hosted on a server."""
        domain = [Service | DataStore]
        range = [Server]

    class monitoredBy(ObjectProperty):
        """A component is watched by a monitoring tool."""
        domain = [Component]
        range = [MonitoringTool]

    class hasAlert(ObjectProperty):
        """A component has an alert raised about it."""
        domain = [Component]
        range = [Alert]

    class affects(ObjectProperty):
        """An incident disrupts a component."""
        domain = [Incident]
        range = [Component]

    # Functional: each component has at most one owning team.
    class ownedBy(ObjectProperty, FunctionalProperty):
        """A component is the responsibility of a team."""
        domain = [Component]
        range = [Team]

    class shouldNotify(ObjectProperty):
        """An incident requires a team to be notified. Filled in by rule 6."""
        domain = [Incident]
        range = [Team]


    # ==========================================================
    # SECTION 3: DATA PROPERTIES (3 in total)
    # These link an individual to a value. All are functional
    # because a server has one reading of each metric at a time.
    # Values must be floats (95.0, not 95).
    # ==========================================================

    class cpuUsage(DataProperty, FunctionalProperty):
        """CPU usage of a server as a percentage, for example 95.0."""
        domain = [Server]
        range = [float]

    class memoryUsage(DataProperty, FunctionalProperty):
        """Memory usage of a server as a percentage, for example 77.0."""
        domain = [Server]
        range = [float]

    class diskUsage(DataProperty, FunctionalProperty):
        """Disk usage of a server as a percentage, for example 35.0."""
        domain = [Server]
        range = [float]


    # ==========================================================
    # SECTION 4: DISJOINTNESS AXIOMS (8 groups)
    # Classes in the same group cannot share any individual.
    # HealthyComponent and FailedComponent are NOT disjoint with
    # any type class, so a server can be both a Server and failed.
    # ==========================================================

    AllDisjoint([Component, Alert, Incident, Team, MonitoringTool])
    AllDisjoint([Service, DataStore, Infrastructure])
    AllDisjoint([CustomerFacingService, InternalService])
    AllDisjoint([Database, Cache])
    AllDisjoint([Server, LoadBalancer, MessageQueue])
    AllDisjoint([CriticalAlert, WarningAlert])
    AllDisjoint([CriticalIncident, MinorIncident])
    AllDisjoint([HealthyComponent, FailedComponent])


    # ==========================================================
    # SECTION 5: DEFINED CLASSES (2)
    # The reasoner puts individuals into these automatically
    # when they meet the condition.
    # ==========================================================

    # A server with CPU usage above 90.0 is an OverloadedServer (rule 5).
    OverloadedServer.equivalent_to.append(
        Server & cpuUsage.some(ConstrainedDatatype(float, min_exclusive=90.0))
    )

    # A component directly depended on by at least 3 services is high impact.
    # This must use the direct property: OWL DL does not allow cardinality
    # restrictions on transitive properties or their inverses.
    HighImpactComponent.equivalent_to.append(
        Component & isDirectlyDependedOnBy.min(3, Service)
    )


    # ==========================================================
    # SECTION 6: CARDINALITY RESTRICTIONS (2)
    # ==========================================================

    # Every incident affects at least one component.
    Incident.is_a.append(affects.min(1, Component))

    # Every component is owned by exactly one team.
    Component.is_a.append(ownedBy.exactly(1, Team))


# ==============================================================
# SECTION 7: CHECKS AND SAVE
# ==============================================================

# These counts confirm nothing is missing or duplicated.
print("Classes:", len(list(onto.classes())), "(expected 24)")
print("Object properties:", len(list(onto.object_properties())), "(expected 9)")
print("Data properties:", len(list(onto.data_properties())), "(expected 3)")

# directlyDependsOn must be a subproperty of dependsOn but must NOT be
# transitive itself, or the HighImpactComponent restriction becomes invalid.
print("directlyDependsOn parents:", directlyDependsOn.is_a, "(expected [buzdim.dependsOn])")
print("directlyDependsOn transitive:", TransitiveProperty in directlyDependsOn.is_a, "(expected False)")

onto.save(file="output/buzdim.owl", format="rdfxml")
print("Saved to output/buzdim.owl")
