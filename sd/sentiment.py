"""Headline sentiment: positive / neutral / negative, scored on your PC (free, no internet needed).

Uses VADER, a small rule-based scorer, plus a finance word list, because plain VADER misses
market language ("Nvidia shares plunge after CEO resignation" scored 0.0 without it).
Scores run from -1 (very negative) to +1 (very positive). This is ROUGH: it reads words, not
meaning, so it gets sarcasm and "already expected" news wrong. Use it as a warning light only.
"""
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Word -> strength from -4 to +4 (VADER's scale). Only market words that VADER misses or misjudges.
FINANCE_WORDS = {
    # negative
    "plunge": -3.0, "plunges": -3.0, "plunged": -3.0, "plummet": -3.0, "plummets": -3.0,
    "crash": -3.5, "crashes": -3.5, "tumble": -2.5, "tumbles": -2.5, "slump": -2.5, "slumps": -2.5,
    "sink": -2.0, "sinks": -2.0, "slide": -1.5, "slides": -1.5, "drop": -1.5, "drops": -1.5,
    "fall": -1.5, "falls": -1.5, "selloff": -2.5, "sell-off": -2.5, "rout": -3.0,
    "downgrade": -2.5, "downgrades": -2.5, "downgraded": -2.5, "miss": -2.0, "misses": -2.0,
    "missed": -2.0, "probe": -2.5, "investigation": -2.0, "lawsuit": -2.5, "sues": -2.5,
    "sued": -2.5, "fraud": -3.5, "recall": -2.0, "layoffs": -2.0, "resignation": -2.0,
    "resigns": -2.0, "ousted": -2.5, "bankruptcy": -3.5, "default": -2.5, "delisting": -3.0,
    "halted": -2.0, "hack": -3.0, "hacked": -3.0, "exploit": -2.5, "outflows": -1.5,
    "bearish": -2.0, "outage": -2.5, "outages": -2.5, "breach": -2.5, "scandal": -3.0,
    "affair": -1.5, "crackdown": -2.0, "ban": -2.0, "bans": -2.0, "sanctions": -2.0, "tariffs": -1.0, "underperform": -2.0, "shortfall": -2.0, "subpoena": -2.5,
    # positive
    "beat": 2.0, "beats": 2.0, "surge": 2.5, "surges": 2.5, "surged": 2.5, "soar": 2.5,
    "soars": 2.5, "jump": 1.5, "jumps": 1.5, "rally": 2.0, "rallies": 2.0, "rebound": 1.5,
    "rebounds": 1.5, "upgrade": 2.5, "upgrades": 2.5, "upgraded": 2.5, "outperform": 2.0,
    "inflows": 1.5, "approval": 2.0, "approved": 2.0, "buyback": 1.5, "bullish": 2.0,
    "record": 1.0, "raises": 1.0, "rises": 1.5, "rise": 1.5, "gains": 1.5, "climbs": 1.5,
    "lowers": -1.0, "slashes": -2.0, "trims": -1.0,
}

_analyzer = SentimentIntensityAnalyzer()
_analyzer.lexicon.update(FINANCE_WORDS)

STRONG_NEGATIVE = -0.5   # at or below this, a headline can trigger the news warning


def score(text):
    """(score from -1 to +1, label)."""
    s = round(_analyzer.polarity_scores(text)["compound"], 3)
    label = "positive" if s >= 0.3 else "negative" if s <= -0.3 else "neutral"
    return s, label
