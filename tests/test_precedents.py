"""Unit tests for the precedent engine's text primitives."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import precedents as P  # noqa: E402


def test_clause_normalization_ignores_names_and_numbers():
    a = P.normalize_clause("If Merrill Kelly records 2+ strikeouts, the market resolves Yes.")
    b = P.normalize_clause("If Mason Adams records 7+ strikeouts, the market resolves Yes.")
    assert a == b


def test_issue_clauses_follow_the_review_class():
    row = {
        "rules": "Interim or acting leaders do not qualify unless announced as the permanent leader. "
        "The market closes at 10:00 AM ET."
    }
    clauses = P.issue_clauses(row, "interpretive_criteria")
    assert len(clauses) == 1 and "permanent" in clauses[0]["text"]


def test_selection_agreement():
    assert P.agrees("Initial official release controls", "The initial official release controls")
    assert not P.agrees("Death counts as leaving office", "Only resignation or removal counts")


def test_ask_terms_bridge_everyday_wording():
    assert "death" in P.ask_terms("What if the leader dies?")
    assert "interim" in P.ask_terms("Do acting leaders count?")
    assert "leave" in P.ask_terms("the vacancy date")


def test_same_template_scores_above_threshold():
    rows = [
        {"title": "Over 5.5 2Q points scored", "rules": "If more than 5.5 points are scored in Q2 of the game, Yes."},
        {"title": "Over 7.5 3Q points scored", "rules": "If more than 7.5 points are scored in Q3 of the game, Yes."},
        {"title": "Will it rain in Paris?", "rules": "Resolves Yes if Meteo France reports rain at CDG."},
    ]
    corpus = P.Corpus(rows)
    v = [corpus.vectors(r) for r in rows]
    assert corpus.similarity(v[0], v[1]) > corpus.similarity(v[0], v[2])
