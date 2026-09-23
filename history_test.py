"""Verify prior-conference intelligence is matched and fed into the debrief."""

from __future__ import annotations

from datetime import date

from core.schema import ClientProfile, InsightCard
from core.synth import build_debrief, historical_delta, new_developments


def card(**kw) -> InsightCard:
    return InsightCard(**kw)


PRIOR = [
    card(conference="Obesity Week 2025", asset="Retatrutide", company="Eli Lilly",
         indication="Obesity", trial_name="TRIUMPH-1", phase="Phase 2",
         key_message="Proof of concept, not yet separated from tirzepatide.",
         data_points=["-17.5% weight reduction at week 48"]),
    card(conference="Obesity Week 2025", asset="CagriSema", company="Novo Nordisk",
         indication="Obesity", key_message="Led on headline weight loss magnitude.",
         data_points=["-22.7% at week 68"]),
    card(conference="Obesity Week 2025", company="Boehringer Ingelheim",
         indication="MASH", asset="", key_message="MASH programme in early Phase 2."),
]

CURRENT = [
    # exact asset match, different spelling/suffix
    card(conference="Obesity Week 2026", asset="Retatrutide (LY-3437943)",
         company="Eli Lilly", indication="Obesity", trial_name="TRIUMPH-4", phase="Phase 3",
         key_message="Triple agonism now the efficacy leader.",
         data_points=["-24.2% weight reduction at week 48"]),
    # match via company + indication, asset renamed
    card(conference="Obesity Week 2026", asset="Survodutide", company="Boehringer Ingelheim",
         indication="MASH", key_message="Sequencing MASH ahead of obesity."),
    # no prior intelligence at all
    card(conference="Obesity Week 2026", asset="MariTide", company="Amgen",
         indication="Obesity", key_message="Monthly dosing is the differentiator."),
]


def main() -> None:
    deltas = historical_delta(CURRENT, PRIOR)
    bases = {d["asset"]: d["basis"] for d in deltas}
    print(f"matched {len(deltas)} card(s) against prior intelligence")
    for asset, basis in bases.items():
        print(f"  {asset:<28} matched on {basis}")

    assert len(deltas) == 2, f"expected 2 matches, got {len(deltas)}"
    assert any("Retatrutide" in a for a in bases), "normalised asset match failed"
    assert any(b == "same company and indication" for b in bases.values()), \
        "company+indication fallback failed"

    fresh = new_developments(CURRENT, PRIOR)
    print(f"\nnew this year: {[c.asset for c in fresh]}")
    assert len(fresh) == 1 and fresh[0].asset == "MariTide", "new-development detection failed"

    client = ClientProfile(name="Test Client", therapeutic_areas=["Obesity"],
                           competitors=["Eli Lilly", "Amgen"])
    debrief = build_debrief(CURRENT, client, "Obesity Week 2026", date.today(), PRIOR)
    headings = [s.heading for s in debrief.sections]
    print(f"\nsections: {headings}")

    assert "Movement versus prior conference intelligence" in headings, "delta section missing"
    assert "New since the last conference" in headings, "new-developments section missing"
    assert "prior" in debrief.executive_summary.lower() or \
           "2025" in debrief.executive_summary, \
           "history not referenced in the executive summary"

    print(f"\nexec summary:\n  {debrief.executive_summary}")
    print("\nHISTORY INTEGRATION OK")


if __name__ == "__main__":
    main()
