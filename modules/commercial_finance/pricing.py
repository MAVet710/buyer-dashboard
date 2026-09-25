"""Shared customer rule semantics; callers supply a canonical channel base price."""

def customer_price(rule, base_price):
    if rule is not None and float(rule.price_usd or 0) > 0:
        return float(rule.price_usd)
    if base_price is None:
        return None
    return max(0.0, float(base_price) * (1 - float(rule.discount_pct or 0) / 100.0)) if rule else float(base_price)
