"""Indian number formatting utilities."""


def format_inr(value, decimals: int = 2) -> str:
    """Format a number in Indian notation (lakhs/crores)."""
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"

    if abs(value) >= 1e7:
        return f"₹{value/1e7:.{decimals}f} Cr"
    elif abs(value) >= 1e5:
        return f"₹{value/1e5:.{decimals}f} L"
    else:
        return f"₹{value:,.{decimals}f}"


def format_market_cap(value_inr) -> str:
    """Format market cap in crores."""
    if value_inr is None:
        return "N/A"
    try:
        cr = float(value_inr) / 1e7
    except (TypeError, ValueError):
        return "N/A"
    if cr >= 1e5:
        return f"₹{cr/1e5:.2f}L Cr"
    elif cr >= 1000:
        return f"₹{cr/1000:.2f}K Cr"
    return f"₹{cr:.0f} Cr"


def format_pct(value, decimals: int = 2, show_sign: bool = True) -> str:
    if value is None:
        return "N/A"
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return "N/A"
    prefix = "+" if show_sign and pct > 0 else ""
    return f"{prefix}{pct:.{decimals}f}%"


def color_for_change(value) -> str:
    """Return 'green' or 'red' based on positive/negative value."""
    try:
        return "green" if float(value) >= 0 else "red"
    except (TypeError, ValueError):
        return "gray"


def confidence_stars(n: int) -> str:
    return "★" * n + "☆" * (5 - n)
