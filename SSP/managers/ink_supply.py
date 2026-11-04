# managers/ink_supply.py
#
# Ink supply rules (docs/remaining-work.md 2.5). The Smart Tank has no tank sensors,
# so the levels are estimates from page coverage and the customer can't see the tanks
# inside the enclosure. So:
#   - low ink only alerts the operator (an SMS once per tank until it's topped up);
#   - customers are blocked only when an admin marks a tank empty, by entering 0%;
#   - the estimate itself never reaches 0, it stops at ESTIMATE_FLOOR.

INK_COLOURS = ('cyan', 'magenta', 'yellow', 'black')

# The print-by-print estimate stops here, so only an admin's own 0% means "empty".
ESTIMATE_FLOOR = 1.0


def estimated_level_after(current: float, cost: float) -> float:
    """A tank's level after a job costing `cost` percent. Never drops below ESTIMATE_FLOOR;
    a tank already at or under the floor (e.g. marked empty at 0) is left where it is."""
    return max(min(current, ESTIMATE_FLOOR), current - cost)


def empty_cartridges(levels) -> dict:
    """{colour: level} for each tank an admin has marked empty (0%); {} if none or unknown."""
    if not levels:
        return {}
    return {name: levels[name] for name in INK_COLOURS if name in levels and levels[name] <= 0}


def low_ink_alerts(levels, already_alerted, threshold):
    """Which tanks newly need an operator alert.

    Returns (to_alert, alerted): `to_alert` is {colour: level} for tanks at or below
    `threshold` that haven't been alerted yet; `alerted` is the set to store, i.e. every
    tank at or below the threshold. A tank topped back above it drops out, which re-arms it.
    """
    low = {name: levels[name] for name in INK_COLOURS if name in (levels or {}) and levels[name] <= threshold}
    to_alert = {name: level for name, level in low.items() if name not in already_alerted}
    return to_alert, set(low)


def parse_alerted(value) -> set:
    """The stored `ink_low_alerted` setting (comma separated colours) as a set."""
    if not value or not isinstance(value, str):
        return set()
    return {part.strip() for part in value.split(',') if part.strip() in INK_COLOURS}


def format_alerted(alerted) -> str:
    return ','.join(name for name in INK_COLOURS if name in alerted)


def low_ink_message(low: dict) -> str:
    """The operator SMS for newly low tanks."""
    parts = ', '.join(f"{name.capitalize()} {level:.0f}%" for name, level in low.items())
    return f"ALERT: Ink is low (estimated: {parts}). Please check the tanks."
