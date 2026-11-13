"""Small, plain-Python indicator helpers (no pandas needed, easy to check by hand)."""


def sma(values, n):
    """Simple moving average of the last n values, or None if there aren't n values yet."""
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def pct(a, b):
    """Percent change from b to a: pct(110, 100) = 10.0"""
    return (a / b - 1) * 100 if b else None


def floats(rows, column):
    return [float(r[column]) for r in rows if r.get(column) not in ("", None)]
