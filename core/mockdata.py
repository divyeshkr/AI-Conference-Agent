"""Deterministic stand-in content so the app runs end to end without API keys.

Two jobs: let the team build before credentials land, and act as the demo-day
fallback if conference wifi or the API endpoint misbehaves.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_CARDS: list[dict[str, Any]] = [
    {
        "title": "Retatrutide Phase 3 48-week weight reduction readout",
        "company": "Eli Lilly",
        "asset": "Retatrutide",
        "indication": "Obesity",
        "trial_name": "TRIUMPH-4",
        "phase": "Phase 3",
        "key_message": "Triple agonism delivers weight reduction beyond the tirzepatide benchmark, positioning retatrutide as the efficacy leader in obesity.",
        "data_points": [
            "-24.2% mean body weight reduction at week 48 vs -3.1% placebo",
            "68% of participants achieved >=20% weight loss",
            "GI adverse events 42%, discontinuation due to AE 6.1%",
        ],
        "competitor_mentions": ["Novo Nordisk", "Amgen"],
        "kol_quote": "We are now firmly in the bariatric-surgery-equivalent range of pharmacotherapy.",
        "session_name": "Late-Breaking Clinical Trials I",
        "themes": ["obesity", "incretin combination therapy", "efficacy ceiling"],
        "confidence": 0.91,
        "is_unpublished": False,
    },
    {
        "title": "CagriSema cardiometabolic subgroup analysis",
        "company": "Novo Nordisk",
        "asset": "CagriSema",
        "indication": "Obesity with type 2 diabetes",
        "trial_name": "REDEFINE-2",
        "phase": "Phase 3",
        "key_message": "Novo is repositioning CagriSema on cardiometabolic risk reduction rather than head-to-head weight loss, signalling a defensive pivot.",
        "data_points": [
            "-13.7% weight reduction in the T2D subgroup",
            "HbA1c reduction of 2.2 percentage points",
            "Systolic BP -7.4 mmHg vs placebo",
        ],
        "competitor_mentions": ["Eli Lilly"],
        "kol_quote": "The conversation is shifting from how much weight to which weight and what it does to the heart.",
        "session_name": "Symposium: Beyond the Scale",
        "themes": ["obesity", "cardiometabolic outcomes", "positioning shift"],
        "confidence": 0.86,
        "is_unpublished": False,
    },
    {
        "title": "MariTide monthly dosing booth messaging",
        "company": "Amgen",
        "asset": "MariTide (maridebart cafraglutide)",
        "indication": "Obesity",
        "trial_name": "MARITIME-1",
        "phase": "Phase 2",
        "key_message": "Amgen's entire booth narrative is built on dosing convenience — monthly or less-frequent administration as the differentiator against weekly incretins.",
        "data_points": [
            "Monthly subcutaneous dosing, Q8W explored in extension",
            "-20% weight reduction at week 52 sustained 150 days post-treatment",
        ],
        "competitor_mentions": ["Eli Lilly", "Novo Nordisk"],
        "kol_quote": "If the weight stays off after you stop, the whole chronic-therapy economic model changes.",
        "session_name": "Exhibit Hall — Booth 412",
        "themes": ["dosing convenience", "weight maintenance", "obesity"],
        "confidence": 0.78,
        "is_unpublished": True,
    },
    {
        "title": "Oral GLP-1 competitive landscape overview",
        "company": "Structure Therapeutics",
        "asset": "Aleniglipron (GSBR-1290)",
        "indication": "Obesity",
        "trial_name": "ACCESS",
        "phase": "Phase 2b",
        "key_message": "Small-molecule oral GLP-1s are converging on ~12% weight loss, making tolerability and manufacturing scale the real battleground rather than efficacy.",
        "data_points": [
            "-12.1% placebo-adjusted weight reduction at week 36",
            "No food or water restriction required for dosing",
        ],
        "competitor_mentions": ["Eli Lilly", "Pfizer", "Novo Nordisk", "Viking Therapeutics"],
        "kol_quote": "",
        "session_name": "Oral Abstract Session: Novel Therapeutics",
        "themes": ["oral GLP-1", "obesity", "manufacturing capacity"],
        "confidence": 0.83,
        "is_unpublished": False,
    },
    {
        "title": "Payer panel on obesity reimbursement thresholds",
        "company": "Multi-stakeholder",
        "asset": "",
        "indication": "Obesity",
        "trial_name": "",
        "phase": "",
        "key_message": "US payers signalled they will require cardiovascular or renal outcomes data, not weight loss alone, for unrestricted formulary access from 2027.",
        "data_points": [
            "3 of 4 panellists indicated step-through requirements will persist",
            "Cited annual budget impact of $9-14bn per plan at current uptake",
        ],
        "competitor_mentions": [],
        "kol_quote": "Weight loss is not a reimbursable outcome. Events avoided are.",
        "session_name": "Market Access Forum",
        "themes": ["reimbursement", "outcomes evidence", "access strategy"],
        "confidence": 0.74,
        "is_unpublished": True,
    },
    {
        "title": "Muscle preservation combination strategies",
        "company": "Regeneron",
        "asset": "Trevogrumab + semaglutide",
        "indication": "Obesity — lean mass preservation",
        "trial_name": "COURAGE",
        "phase": "Phase 2",
        "key_message": "Lean-mass preservation is emerging as the next differentiation axis, with myostatin inhibition combined with incretins the leading approach.",
        "data_points": [
            "Lean mass loss reduced from 40% to 18% of total weight lost",
            "No offset in total weight reduction observed",
        ],
        "competitor_mentions": ["Eli Lilly", "Scholar Rock"],
        "kol_quote": "Quality of weight loss will define the second generation of these drugs.",
        "session_name": "Symposium: Body Composition Matters",
        "themes": ["lean mass", "combination therapy", "next-generation obesity"],
        "confidence": 0.8,
        "is_unpublished": False,
    },
    {
        "title": "Real-world persistence and discontinuation data",
        "company": "IQVIA / academic collaboration",
        "asset": "GLP-1 class",
        "indication": "Obesity",
        "trial_name": "",
        "phase": "Real-world evidence",
        "key_message": "Roughly half of patients discontinue within 12 months, and the field is now openly treating persistence as the biggest commercial risk.",
        "data_points": [
            "52% discontinuation at 12 months in commercial claims",
            "Median time to discontinuation 6.8 months",
            "Weight regain of 60% of lost weight within 12 months of stopping",
        ],
        "competitor_mentions": [],
        "kol_quote": "The market is far smaller than the prescription numbers suggest if nobody stays on therapy.",
        "session_name": "Real-World Evidence Session",
        "themes": ["persistence", "real-world evidence", "commercial risk"],
        "confidence": 0.88,
        "is_unpublished": False,
    },
    {
        "title": "Competitor field-team intelligence from 1:1 discussion",
        "company": "Boehringer Ingelheim",
        "asset": "Survodutide",
        "indication": "MASH and obesity",
        "trial_name": "SYNCHRONIZE",
        "phase": "Phase 3",
        "key_message": "BI is deliberately sequencing MASH ahead of obesity to secure a differentiated label and avoid a direct efficacy comparison in obesity.",
        "data_points": [
            "83% MASH resolution at highest dose reported in Phase 2",
            "Obesity filing intentionally timed after MASH approval",
        ],
        "competitor_mentions": ["Madrigal", "Novo Nordisk"],
        "kol_quote": "They told me the obesity indication is a follow-on, not the lead — that is a change from last year.",
        "session_name": "1:1 discussion — medical affairs lead",
        "themes": ["MASH", "indication sequencing", "label differentiation"],
        "confidence": 0.65,
        "is_unpublished": True,
    },
]

_HISTORICAL: list[dict[str, Any]] = [
    {
        "title": "Retatrutide Phase 2 interim weight reduction",
        "company": "Eli Lilly",
        "asset": "Retatrutide",
        "indication": "Obesity",
        "trial_name": "TRIUMPH-1",
        "phase": "Phase 2",
        "key_message": "Early triple-agonist data established proof of concept but efficacy was not yet separated from tirzepatide.",
        "data_points": ["-17.5% mean weight reduction at week 48"],
        "competitor_mentions": ["Novo Nordisk"],
        "kol_quote": "",
        "session_name": "Late-Breaking Clinical Trials",
        "themes": ["obesity", "incretin combination therapy"],
        "confidence": 0.9,
        "is_unpublished": False,
    },
    {
        "title": "CagriSema positioned on weight loss magnitude",
        "company": "Novo Nordisk",
        "asset": "CagriSema",
        "indication": "Obesity",
        "trial_name": "REDEFINE-1",
        "phase": "Phase 3",
        "key_message": "Novo led with headline weight loss magnitude as the primary competitive claim.",
        "data_points": ["-22.7% weight reduction at week 68"],
        "competitor_mentions": ["Eli Lilly"],
        "kol_quote": "",
        "session_name": "Plenary Session",
        "themes": ["obesity", "efficacy positioning"],
        "confidence": 0.9,
        "is_unpublished": False,
    },
    {
        "title": "Oral GLP-1 field at early stage",
        "company": "Pfizer",
        "asset": "Danuglipron",
        "indication": "Obesity",
        "trial_name": "",
        "phase": "Phase 2b",
        "key_message": "Oral GLP-1 development dominated by tolerability concerns, with high discontinuation limiting enthusiasm.",
        "data_points": ["Discontinuation rates above 50% in Phase 2b"],
        "competitor_mentions": ["Eli Lilly"],
        "kol_quote": "",
        "session_name": "Oral Abstract Session",
        "themes": ["oral GLP-1", "tolerability"],
        "confidence": 0.85,
        "is_unpublished": False,
    },
]


def _pick(seed: str, pool: list[dict[str, Any]]) -> dict[str, Any]:
    idx = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(pool)
    return dict(pool[idx])


def historical_cards() -> list[dict[str, Any]]:
    return [dict(c) for c in _HISTORICAL]


def mock_json(key: str, prompt: str) -> dict[str, Any]:
    if key == "extract":
        card = _pick(prompt, _CARDS)
        card["verbatim"] = _snippet(prompt)
        return {"cards": [card], "_mock": True}
    return {"_mock": True}


def _snippet(prompt: str) -> str:
    body = prompt.split("---", 1)[-1].strip()
    body = re.sub(r"\s+", " ", body)
    return body[:280] if body else "(mock extraction — no source text available)"


def mock_text(prompt: str) -> str:
    return (
        "Mock narrative generated without an API call. Connect a provider on the "
        "Setup page to produce model-written prose. The structure, data points and "
        "citations shown here are assembled from your actual uploaded materials."
    )
