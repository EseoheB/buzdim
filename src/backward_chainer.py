"""
backward_chainer.py

A goal-driven (backward chaining) engine for BuzDim, written in Python.
It answers CQ3: "What is the root cause of the checkout_service outage?"

Backward chaining starts from a goal, such as AffectedService(checkout_service),
finds the rules that could conclude it, and tries to prove each rule's
conditions as subgoals, until it reaches asserted facts. Every step is
printed with indentation, so the trace reads as a proof tree.

After the proof, the engine looks for root causes: failed components with
nothing failed upstream of them (neither a dependency nor the server they
run on). This needs "has no failed dependency", a negative check that SWRL
cannot express, which is why this logic lives in Python.

Four investigations are run:
    1. CQ3, main data: why is checkout_service affected?
    2. Main data: is search_service affected? (a goal that cannot be proven)
    3. Scenario B: why is web_frontend affected? (two root causes)
    4. Edge case: a circular dependency between two services

The rules used are the same as in forward_chainer.py:
    Rule 1: critical alert          -> FailedComponent
    Rule 2: depends on failed       -> AffectedService
    Rule 3: runs on failed server   -> AffectedService
    Rule 7: depends on affected     -> AffectedService

Run from the project root, after populate.py:
    python src/backward_chainer.py
"""

import forward_chainer as fc


def is_failed(kb, component):
    """Rule 1 as a quiet check: True if the component has a critical alert."""
    return any(kb.is_a(a, "CriticalAlert") for a in kb.objects("hasAlert", component))


def upstream_components(kb, component):
    """
    Return everything the component relies on: its dependencies and the
    servers it runs on, followed step by step.

    The seen set stops the search from looping forever if the dependency
    graph contains a cycle.
    """
    seen = set()
    stack = [component]
    while stack:
        current = stack.pop()
        for nxt in kb.objects("dependsOn", current) + kb.objects("runsOn", current):
            if nxt != component and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return sorted(seen)


class BackwardChainer:
    """Proves goals by working backward through the rules, printing a proof trace."""

    def __init__(self, kb):
        self.kb = kb
        self.failed_found = set()   # failed components reached during the proof
        self.failed_cache = {}      # component -> result, so each one is checked once

    def say(self, depth, text):
        """Print one line of the trace, indented by its depth in the proof tree."""
        print("  " * depth + text)

    def prove_failed(self, component, depth):
        """Goal: FailedComponent(component). Only rule 1 can conclude this."""
        if component in self.failed_cache:
            result = self.failed_cache[component]
            status = "failed" if result else "not failed"
            self.say(depth, f"FailedComponent({component}) already checked: {status}")
            return result

        self.say(depth, f"Goal: FailedComponent({component})?")
        for alert in self.kb.objects("hasAlert", component):
            if self.kb.is_a(alert, "CriticalAlert"):
                self.say(depth + 1, f"Rule 1: {component} has critical alert {alert}. PROVEN")
                self.failed_cache[component] = True
                self.failed_found.add(component)
                return True

        self.say(depth + 1, f"Rule 1: {component} has no critical alert. Not proven")
        self.failed_cache[component] = False
        return False

    def prove_affected(self, service, depth, path):
        """
        Goal: AffectedService(service). Rules 3, 2, and 7 can conclude this.

        All three rules are tried, even after one succeeds, so that every
        failure reaching the service is found. path holds the services on
        the current chain of reasoning, to detect circular dependencies.
        """
        self.say(depth, f"Goal: AffectedService({service})?")

        if service in path:
            cycle = " -> ".join(path + [service])
            self.say(depth + 1, f"Cycle detected: {cycle}. Skipping this branch")
            return False
        path = path + [service]
        proven = False

        for server in self.kb.objects("runsOn", service):
            if self.kb.is_a(server, "Server"):
                self.say(depth + 1, f"Try rule 3: {service} runs on server {server}")
                if self.prove_failed(server, depth + 2):
                    proven = True

        for dependency in self.kb.objects("dependsOn", service):
            self.say(depth + 1, f"Try rule 2: {service} depends on {dependency}")
            if self.prove_failed(dependency, depth + 2):
                proven = True

        for dependency in self.kb.objects("dependsOn", service):
            if self.kb.is_a(dependency, "Service"):
                self.say(depth + 1, f"Try rule 7: {service} depends on service {dependency}")
                if self.prove_affected(dependency, depth + 2, path):
                    proven = True

        result = "PROVEN" if proven else "NOT PROVEN"
        self.say(depth + 1, f"Result: AffectedService({service}) {result}")
        return proven


def find_root_causes(kb, failed_components):
    """
    A failed component is a root cause if nothing upstream of it has failed.
    Returns the root causes and prints the reasoning for each candidate.
    """
    roots = []
    for component in sorted(failed_components):
        upstream = upstream_components(kb, component)
        failed_upstream = [u for u in upstream if is_failed(kb, u)]
        if failed_upstream:
            print(f"  {component} is NOT a root cause: it relies on failed {failed_upstream}")
        else:
            checked = upstream if upstream else "nothing"
            print(f"  {component} IS a root cause: nothing it relies on has failed (checked: {checked})")
            roots.append(component)
    return roots


def investigate(kb, service, title, expected):
    """Run one backward chaining investigation and print the full trace."""
    print("=" * 70)
    print(title)
    print("=" * 70)

    chainer = BackwardChainer(kb)
    proven = chainer.prove_affected(service, 1, [])
    print()

    if not proven:
        print(f"Conclusion: {service} is not affected, so there is no root cause to find.")
        print(f"    expected: {expected}")
        print()
        return

    print(f"Failed components reached by the proof: {sorted(chainer.failed_found)}")
    print("Root cause analysis:")
    roots = find_root_causes(kb, chainer.failed_found)
    if roots:
        print(f"Root cause(s): {roots}")
    else:
        print("No single root cause found: every failed component relies on another failed one.")
    print(f"    expected: {expected}")
    print()


def main():
    base_kb = fc.load_knowledge_base()
    fc.apply_subproperty_axiom(base_kb)

    # 1. CQ3 on the main data
    investigate(
        base_kb.copy(), "checkout_service",
        "Investigation 1 (CQ3): why is checkout_service affected? (main data)",
        "root cause ['orders_db']",
    )

    # 2. A goal that cannot be proven
    investigate(
        base_kb.copy(), "search_service",
        "Investigation 2: is search_service affected? (main data)",
        "not affected",
    )

    # 3. Scenario B: a critical alert also arrives on server_a
    kb_b = base_kb.copy()
    kb_b.types["alert_005"].update({"Alert", "CriticalAlert"})
    kb_b.relations.add(("hasAlert", "server_a", "alert_005"))
    investigate(
        kb_b, "web_frontend",
        "Investigation 3: why is web_frontend affected? (scenario B, critical alert on server_a)",
        "root causes ['orders_db', 'server_a']",
    )

    # 4. Edge case: payment_service is wrongly configured to depend on
    #    checkout_service, which already depends on payment_service.
    kb_cycle = base_kb.copy()
    kb_cycle.relations.add(("directlyDependsOn", "payment_service", "checkout_service"))
    kb_cycle.relations.add(("dependsOn", "payment_service", "checkout_service"))
    investigate(
        kb_cycle, "checkout_service",
        "Investigation 4 (edge case): circular dependency between checkout_service and payment_service",
        "cycle detected and skipped, root cause still ['orders_db']",
    )


if __name__ == "__main__":
    main()
