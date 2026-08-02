"""Pure calculations used by the white-label repack workspace."""


GRAMS_PER_POUND = 453.59237
GRAMS_PER_OUNCE = 28.349523125


def grams_from_unit(weight_value: float, weight_unit: str) -> float:
    """Convert a supported bulk-weight value to grams.

    The existing workspace treats values as grams when the unit is not pounds
    or ounces. Keeping that fallback preserves saved-session compatibility.
    """

    if weight_unit == "lb":
        return weight_value * GRAMS_PER_POUND
    if weight_unit == "oz":
        return weight_value * GRAMS_PER_OUNCE
    return weight_value
