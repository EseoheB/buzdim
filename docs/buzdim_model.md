# BuzDim Ontology Design Specification

## 1. Overview

- **Ontology name:** BuzDim (file `buzdim.owl`, IRI `http://www.example.org/buzdim.owl#`)
- **System modeled:** the infrastructure of a fictional online store called ShopLite
- **Purpose:** take alerts and component facts, then infer which services are affected, how severe each incident is, which team to notify, and the likely root cause
- **Implementation:** Python with owlready2 (Option C)
- **Reasoners:** HermiT for consistency and classification. Pellet only if rules that need SWRL built-ins are added later.

## 2. Class hierarchy (24 classes)

```
owl:Thing
    Component
        Service
            CustomerFacingService
            InternalService
            AffectedService
        DataStore
            Database
            Cache
        Infrastructure
            Server
                OverloadedServer
            LoadBalancer
            MessageQueue
        HealthyComponent
        FailedComponent
        HighImpactComponent
    Alert
        CriticalAlert
        WarningAlert
    Incident
        CriticalIncident
        MinorIncident
    Team
    MonitoringTool
```

### How each special class gets its members

| Class | Type | How members are assigned |
|---|---|---|
| `OverloadedServer` | Defined | Equivalent to: `Server` and `cpuUsage` some float > 90.0 |
| `HighImpactComponent` | Defined | Equivalent to: `Component` and `isDirectlyDependedOnBy` min 3 `Service` |
| `FailedComponent` | Rule-inferred | Rule 1 |
| `AffectedService` | Rule-inferred | Rules 2, 3, and 7 |
| `CriticalIncident` | Rule-inferred | Rule 4 |
| `MinorIncident` | Python step | Assigned after reasoning to incidents not classified as critical (closed-world decision) |
| `HealthyComponent` | Asserted | Used only in the Q12 conflict test |

## 3. Axioms

### Disjointness

1. `Component`, `Alert`, `Incident`, `Team`, `MonitoringTool`
2. `Service`, `DataStore`, `Infrastructure`
3. `CustomerFacingService`, `InternalService`
4. `Database`, `Cache`
5. `Server`, `LoadBalancer`, `MessageQueue`
6. `CriticalAlert`, `WarningAlert`
7. `CriticalIncident`, `MinorIncident`
8. `HealthyComponent`, `FailedComponent`

Do not declare `HealthyComponent` or `FailedComponent` disjoint with any type class. A server must be able to be a `Server` and a `FailedComponent` at the same time.

### Cardinality

- Every `Incident` affects at least 1 `Component`
- Every `Component` is owned by exactly 1 `Team`

### Distinctness

- `AllDifferent` over all 28 individuals. This is needed for the Q7 count and so that a component given two owners is flagged as an error instead of the two teams being merged.

### Predicate logic forms

- Transitivity: ∀x,y,z (dependsOn(x,y) ∧ dependsOn(y,z) → dependsOn(x,z))
- Subproperty: ∀x,y (directlyDependsOn(x,y) → dependsOn(x,y))
- Inverse: ∀x,y (directlyDependsOn(x,y) ↔ isDirectlyDependedOnBy(y,x))
- Disjointness: ∀x (HealthyComponent(x) → ¬FailedComponent(x))
- Functional: ∀x,t1,t2 (ownedBy(x,t1) ∧ ownedBy(x,t2) → t1 = t2)
- Overloaded: ∀s (OverloadedServer(s) ↔ Server(s) ∧ ∃u (cpuUsage(s,u) ∧ u > 90.0))
- High impact: ∀x (HighImpactComponent(x) ↔ Component(x) ∧ ∃≥3 y (isDirectlyDependedOnBy(x,y) ∧ Service(y)))

## 4. Properties

### Object properties

| Property | Domain → Range | Characteristics |
|---|---|---|
| `dependsOn` | Component → Component | Transitive |
| `directlyDependsOn` | Component → Component | Subproperty of `dependsOn` |
| `isDirectlyDependedOnBy` | Component → Component | Inverse of `directlyDependsOn` |
| `runsOn` | Service or DataStore → Server | |
| `monitoredBy` | Component → MonitoringTool | |
| `hasAlert` | Component → Alert | |
| `affects` | Incident → Component | |
| `ownedBy` | Component → Team | Functional |
| `shouldNotify` | Incident → Team | Inferred by rule 6 |

### Data properties

| Property | Domain → Range | Characteristics |
|---|---|---|
| `cpuUsage` | Server → float | Functional |
| `memoryUsage` | Server → float | Functional |
| `diskUsage` | Server → float | Functional |

### Notes

- Only `directlyDependsOn` is asserted. The reasoner fills in `dependsOn` (through the subproperty link and transitivity) and `isDirectlyDependedOnBy` (through the inverse).
- The cardinality restriction for `HighImpactComponent` must use `isDirectlyDependedOnBy`. Transitive properties and their inverses cannot be used in cardinality restrictions in OWL DL.
- Store all metric values as floats (95.0, not 95) so they match the float datatype restriction.
- Domains are not checks. The reasoner uses them to infer class membership, so a domain that is too narrow can make the ontology inconsistent.

## 5. Production rules

| # | Rule in plain words | Predicate logic |
|---|---|---|
| 1 | A component with a critical alert is failed | ∀c,a (Component(c) ∧ hasAlert(c,a) ∧ CriticalAlert(a) → FailedComponent(c)) |
| 2 | A service that depends on a failed component is affected | ∀s,c (Service(s) ∧ dependsOn(s,c) ∧ FailedComponent(c) → AffectedService(s)) |
| 3 | A service running on a failed server is affected | ∀s,v (Service(s) ∧ runsOn(s,v) ∧ Server(v) ∧ FailedComponent(v) → AffectedService(s)) |
| 4 | An incident affecting a customer-facing service is critical | ∀i,s (Incident(i) ∧ affects(i,s) ∧ CustomerFacingService(s) → CriticalIncident(i)) |
| 5 | A server with CPU above 90% is overloaded | ∀s,u (Server(s) ∧ cpuUsage(s,u) ∧ u > 90.0 → OverloadedServer(s)) |
| 6 | An incident affecting a component notifies the owning team | ∀i,c,t (Incident(i) ∧ affects(i,c) ∧ ownedBy(c,t) → shouldNotify(i,t)) |
| 7 | A service that depends on an affected service is also affected | ∀s,x (Service(s) ∧ dependsOn(s,x) ∧ AffectedService(x) → AffectedService(s)) |

### SWRL versions (rules 1 to 4, 6, and 7)

```
Component(?c) ^ hasAlert(?c, ?a) ^ CriticalAlert(?a) -> FailedComponent(?c)
Service(?s) ^ dependsOn(?s, ?c) ^ FailedComponent(?c) -> AffectedService(?s)
Service(?s) ^ runsOn(?s, ?v) ^ Server(?v) ^ FailedComponent(?v) -> AffectedService(?s)
Incident(?i) ^ affects(?i, ?s) ^ CustomerFacingService(?s) -> CriticalIncident(?i)
Incident(?i) ^ affects(?i, ?c) ^ ownedBy(?c, ?t) -> shouldNotify(?i, ?t)
Service(?s) ^ dependsOn(?s, ?x) ^ AffectedService(?x) -> AffectedService(?s)
```

### Implementation notes

- Rule 5 is implemented in OWL as the `OverloadedServer` defined class, so it has no SWRL version. HermiT does not support SWRL built-ins such as `swrlb:greaterThan`.
- Rule 6 creates a relationship, so run the reasoner with `infer_property_values=True` to see its results.
- Rule 7 was added after testing. HermiT applied rule 2 only to direct dependencies, because it does not pass links derived from the transitive `dependsOn` property into SWRL rules, so web_frontend was missed. Rule 7 spreads impact one step at a time (cascading impact) and reaches web_frontend through checkout_service. This is a limitation worth discussing in the report.
- The Python forward chainer implements all seven rules as production rules with printed traces.
- The Python backward chainer handles Q5 (root cause). It finds a failed component with no failed dependencies of its own, which SWRL cannot express because it has no negation. It must also handle cycles and cases where no root cause is found.
- `MinorIncident` is assigned in Python after reasoning. Under the open world assumption, the reasoner never concludes an incident is minor just because nothing made it critical.

## 6. Individuals (28)

### Components (14)

| Individual | Class | Owned by | Runs on | Monitored by |
|---|---|---|---|---|
| web_frontend | CustomerFacingService | storefront_team | server_a | prometheus |
| checkout_service | CustomerFacingService | storefront_team | server_b | prometheus |
| search_service | CustomerFacingService | storefront_team | server_a | prometheus |
| payment_service | InternalService | payments_team | server_b | prometheus |
| inventory_service | InternalService | storefront_team | server_c | prometheus |
| orders_db | Database | payments_team | server_c | cloudwatch |
| product_db | Database | storefront_team | server_c | cloudwatch |
| session_cache | Cache | storefront_team | server_b | cloudwatch |
| server_a | Server | platform_team | | cloudwatch |
| server_b | Server | platform_team | | cloudwatch |
| server_c | Server | platform_team | | prometheus |
| server_d | Server (added for Q10) | platform_team | | prometheus |
| load_balancer | LoadBalancer | platform_team | | splunk |
| order_queue | MessageQueue | platform_team | | none |

### Server metrics

| Server | cpuUsage | memoryUsage | diskUsage |
|---|---|---|---|
| server_a | 45.0 | 60.0 | 55.0 |
| server_b | 72.5 | 68.0 | 40.0 |
| server_c | 88.0 | 81.0 | 70.0 |
| server_d | 95.0 | 77.0 | 35.0 |

### Direct dependencies

- web_frontend → checkout_service, search_service, load_balancer
- checkout_service → payment_service, orders_db, session_cache, order_queue
- payment_service → orders_db
- inventory_service → orders_db, product_db, order_queue
- search_service → product_db

### Alerts (4)

| Alert | Class | On component |
|---|---|---|
| alert_001 | CriticalAlert | orders_db |
| alert_002 | WarningAlert | server_c |
| alert_003 | WarningAlert | session_cache |
| alert_004 | WarningAlert | server_d |

### Incidents (4)

| Incident | Affects |
|---|---|
| inc_001 | checkout_service |
| inc_002 | payment_service |
| inc_003 | order_queue |
| inc_004 | search_service |

### Teams (3)

storefront_team, payments_team, platform_team

### Monitoring tools (3)

cloudwatch, prometheus, splunk

## 7. Competency questions and expected answers

| Q | Question | Type | Expected answer |
|---|---|---|---|
| 3 | Which monitoring tool watches each server? | Simple lookup | server_a, server_b → cloudwatch. server_c, server_d → prometheus. |
| 4 | Which services are affected if orders_db fails? | Complex reasoning, forward chaining | Rule 1 makes orders_db failed. checkout_service, payment_service, inventory_service are affected directly. web_frontend is affected indirectly through checkout_service (rule 7). search_service is not affected. |
| 5 | What is the root cause of the checkout_service outage? | Backward chaining | orders_db. It is the only failed dependency, it has no dependencies of its own, and its server (server_c) only has a warning alert, so it is not failed. |
| 7 | Which components are depended on by 3 or more services? | Complex reasoning, cardinality | orders_db only (checkout_service, payment_service, inventory_service). product_db and order_queue have 2 each. |
| 8 | Which incidents are critical and which are minor? | Classification | Critical: inc_001, inc_004. Minor: inc_002, inc_003. Notify: inc_001 and inc_004 → storefront_team, inc_002 → payments_team, inc_003 → platform_team. |
| 10 | How is server_d (95% CPU) classified? | Automatic classification | OverloadedServer. server_c at 88.0 is not. |
| 11 | Which components have no monitoring data? | Edge case: incomplete information | order_queue only. |
| 12 | What happens with conflicting health data? | Edge case: conflicting data | The reasoner reports an inconsistency (scenario C). |

## 8. Test scenarios

Run scenarios B and C on separate copies of the ontology so the main answers in section 7 stay unchanged.

- **Scenario A, main run:** all facts in section 6. Produces the expected answers in section 7.
- **Scenario B, rule 3 demo:** add alert_005 (CriticalAlert) on server_a. Rule 1 makes server_a failed, then rule 3 makes web_frontend and search_service affected. search_service is the key result, since it was not affected in the main run. This also serves as a forward chaining demo: new data arrives and new conclusions follow.
- **Scenario C, Q12 conflict:** add alert_005 (CriticalAlert) on server_a and also assert server_a as a `HealthyComponent`. This models a health check saying healthy while an alert says critical. Rule 1 infers failed, which clashes with the disjointness axiom, so the reasoner reports the ontology as inconsistent. Catch `OwlReadyInconsistentOntologyError` and print a clear explanation.

## 9. Implementation checklist

- [ ] Q3: `Server`, `MonitoringTool`, `monitoredBy`; direct query
- [ ] Q4: transitive `dependsOn`, `FailedComponent`, `AffectedService`; SWRL rules 1, 2, and 7 with reasoner
- [ ] Q5: Python backward chainer with trace, cycle handling, and a "no root cause found" case
- [ ] Q7: `directlyDependsOn`, `isDirectlyDependedOnBy`, `HighImpactComponent`, `AllDifferent`
- [ ] Q8: `CriticalIncident` via rule 4, `MinorIncident` via Python step, `shouldNotify` via rule 6
- [ ] Q10: float `cpuUsage` values and the `OverloadedServer` defined class
- [ ] Q11: Python check for components with no `monitoredBy` link
- [ ] Q12: scenario C on a separate copy, with the inconsistency caught and explained
- [ ] Scenario B: rule 3 demonstrated on a separate copy
