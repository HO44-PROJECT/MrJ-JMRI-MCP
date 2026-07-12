"""Shared sort-by-column support for `list`/`findr`/`findg` across every
read-only listing domain (roster/block/sensor/signal/turnout/light).

Each domain module defines its own `SORT_FIELDS: dict[str, tuple[int, bool]]`
mapping a `by*` choice name (e.g. "bystate") to `(row_index, casefold)` -
the index into that domain's own `_row()` tuple, and whether to casefold
before comparing (True for text columns, False for numbers/dates so "10"
doesn't sort before "9"). `byname` is always index 1 (the label column,
system_id is always index 0 - see the "system_id first column, sorted by
name" convention documented in each domain's `_headers()`).

`sort_rows()`/`mark_sorted_header()` are the only two functions a domain's
list/findr/findg bodies need - everything else (turning SORT_FIELDS into
argparse subcommands) lives in parser.py's `_sort_family()`.
"""


def sort_rows(rows: list[list], sort_fields: dict[str, tuple[int, bool]], sort_by: str) -> list[list]:
    """Sort already-flattened `_row()` tuples by the column `sort_by` names."""
    index, fold = sort_fields[sort_by]
    if fold:
        return sorted(rows, key=lambda r: str(r[index]).casefold())
    return sorted(rows, key=lambda r: (r[index] is None, r[index]))


def mark_sorted_header(headers: list[str], sort_fields: dict[str, tuple[int, bool]], sort_by: str, indicator: str) -> list[str]:
    """Return `headers` with `indicator` appended to whichever column `sort_by` sorts on."""
    index, _fold = sort_fields[sort_by]
    headers = list(headers)
    headers[index] += indicator
    return headers


def split_find_tokens(tokens: list[str], sort_fields: dict[str, tuple[int, bool]]) -> tuple[str | None, str]:
    """Split findr/findg's `pattern_tokens` into `(sort_by, pattern)`.

    `pattern_tokens` is 1 or 2 raw positional tokens (see parser.py's
    `_find_pattern_leaf` for why this isn't nested subparsers). Only the
    first token, and only when it's an exact `SORT_FIELDS` key, is treated
    as a sort word - anything else (including a pattern that happens to
    collide with a `by*` word, or a 2-token case where the first isn't a
    known key) is left as part of the pattern, joined back with a space so
    a legitimate multi-word glob/regex isn't silently truncated.
    """
    if len(tokens) >= 2 and tokens[0] in sort_fields:
        return tokens[0], " ".join(tokens[1:])
    return None, " ".join(tokens)
