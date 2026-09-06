"""Presentation helpers for the identity-rebuild CLI commands: formatting/printing only.

Steps compute and expose results as properties; printing/formatting stays here, called
from ``cli.py`` after a step has finished, never from step-internal code.
"""


def print_zone_tables(tables) -> None:
    for L, table in tables:
        print(f"\n  level {L}: {len(table)} zones")
        for zid, lab, area, nobj in table:
            print(f"    zone {zid:>2}  {lab:<22} area={area:<4} objs={nobj}")


def report_verify(ok: bool, total: int, matched: int, missing, extra) -> bool:
    """Print a VerifyStep result. ``missing``/``extra`` are the Counters it produced."""
    if ok:
        print(f"IDENTITY OK: {matched}/{total} objects match, 0 mismatches")
    else:
        print(f"IDENTITY FAIL: {matched}/{total} match, "
              f"{sum(missing.values())} missing, {sum(extra.values())} extra")
        for k in list(missing)[:5]:
            print("   missing:", k)
        for k in list(extra)[:5]:
            print("   extra:  ", k)
    return ok
