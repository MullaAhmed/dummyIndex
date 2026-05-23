"""Helper utilities for the sample fixture."""
from __future__ import annotations


def format_currency(amount: float, currency: str = "USD") -> str:
    return f"{currency} {amount:.2f}"


def parse_amount(text: str) -> float:
    return float(text.strip().split()[-1])
