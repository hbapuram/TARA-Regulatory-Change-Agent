from datetime import date

from tara import pipeline


def test_course_derives_backward_deadline_from_trigger_date(ctx):
    _determination, actions = pipeline.actions_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2027, 4, 1))
    by_obligation = {a.obligation_id: a for a in actions}
    # OBL-003 (return & payment) has a 30-day lead time off the 2027-03-14 trigger.
    assert by_obligation["OBL-003"].deadline == "2027-02-12"


def test_course_escalates_with_no_owner(ctx):
    _determination, gaps = pipeline.gaps_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2027, 4, 1))
    from tara.agents import course
    actions = course.plan(ctx.domain_pack, gaps, owner=None, atlas=ctx.atlas)
    assert all(a.escalated for a in actions)
    assert all(a.deadline is None for a in actions)


def test_course_only_plans_non_satisfied_gaps(ctx):
    _determination, actions = pipeline.actions_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2026, 9, 6))
    # None satisfied yet (no ANCHOR closures recorded) -> every gap becomes an action.
    assert len(actions) >= 1


def test_course_orders_dependents_after_their_dependency(ctx):
    # OBL-002 is superseded and so is never actually in this plan (it's
    # filtered out upstream) — the real dependency claim to test is
    # OBL-001 (the deemed disposal itself) before both of the things that
    # depend on it, and OBL-002B (the live rate) before OBL-003 (the return
    # that requires the computation to already exist).
    _determination, actions = pipeline.actions_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2027, 4, 1))
    order = [a.obligation_id for a in actions]
    assert {"OBL-001", "OBL-002B", "OBL-003", "OBL-004"} <= set(order)
    assert order.index("OBL-001") < order.index("OBL-002B")
    assert order.index("OBL-001") < order.index("OBL-004")
    assert order.index("OBL-002B") < order.index("OBL-003")


def test_course_clamps_a_dependents_deadline_after_its_dependency(ctx):
    # Even where a naive lead-time-only calculation would put a dependent's
    # deadline before its dependency's, COURSE must never schedule evidence
    # of a computation before the computation itself is due.
    _determination, actions = pipeline.actions_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2027, 4, 1))
    by_obligation = {a.obligation_id: a for a in actions}
    for dependent_id, dependency_id in (("OBL-002B", "OBL-001"), ("OBL-003", "OBL-002B"), ("OBL-004", "OBL-001")):
        dependent = by_obligation[dependent_id]
        dependency = by_obligation[dependency_id]
        assert dependent.deadline > dependency.deadline, (
            f"{dependent_id} ({dependent.deadline}) must fall after {dependency_id} ({dependency.deadline})"
        )
