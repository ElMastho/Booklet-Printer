"""Editable page plan: the reading order of the booklet and per-page adjustments.

The plan is a list of :class:`PageSpec`. Each entry is either a page of the
source document (with optional rotation, crop, scale and offset) or a blank
page. The imposition engine consumes the plan, so every edit made here is
reflected in the preview and in the printed booklet.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Iterable, Optional


@dataclass
class PageSpec:
    source: Optional[int]  # 0-based page of the source document, None = blank page
    rotation: int = 0  # extra clockwise rotation: 0, 90, 180 or 270
    crop_mm: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # left, top, right, bottom
    scale: float = 1.0  # 0.1 .. 1.0, relative to "fit in the half sheet"
    offset_mm: tuple[float, float] = (0.0, 0.0)  # horizontal, vertical shift inside the half sheet

    @property
    def is_blank(self) -> bool:
        return self.source is None

    @property
    def is_adjusted(self) -> bool:
        return (
            self.rotation % 360 != 0
            or any(self.crop_mm)
            or abs(self.scale - 1.0) > 1e-9
            or any(self.offset_mm)
        )

    def reset_adjustments(self) -> "PageSpec":
        return PageSpec(self.source)


def _normalize(indices: Iterable[int], length: int) -> list[int]:
    out = sorted({i for i in indices if 0 <= i < length})
    return out


@dataclass
class PagePlan:
    pages: list[PageSpec] = field(default_factory=list)
    _undo: list[list[PageSpec]] = field(default_factory=list, repr=False)
    _redo: list[list[PageSpec]] = field(default_factory=list, repr=False)

    UNDO_LIMIT = 200

    @classmethod
    def from_count(cls, count: int) -> "PagePlan":
        return cls([PageSpec(i) for i in range(count)])

    def __len__(self) -> int:
        return len(self.pages)

    def __getitem__(self, i: int) -> PageSpec:
        return self.pages[i]

    # ------------------------------------------------------------- history
    def _snapshot(self) -> None:
        self._undo.append(copy.deepcopy(self.pages))
        if len(self._undo) > self.UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.pages)
        self.pages = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.pages)
        self.pages = self._redo.pop()
        return True

    # ---------------------------------------------------------- operations
    # Every operation returns the new indices of the affected pages so that the
    # UI can keep them selected.

    def move(self, indices: Iterable[int], target: int) -> list[int]:
        """Move the pages at ``indices`` so that they start at ``target``
        (an index in the list *before* the move, like a drop position)."""
        idx = _normalize(indices, len(self.pages))
        if not idx:
            return []
        target = max(0, min(len(self.pages), target))
        self._snapshot()
        moving = [self.pages[i] for i in idx]
        before = sum(1 for i in idx if i < target)
        rest = [p for i, p in enumerate(self.pages) if i not in set(idx)]
        pos = target - before
        self.pages = rest[:pos] + moving + rest[pos:]
        return list(range(pos, pos + len(moving)))

    def shift(self, indices: Iterable[int], delta: int) -> list[int]:
        """Move a selection up (delta < 0) or down (delta > 0) by one or more steps."""
        idx = _normalize(indices, len(self.pages))
        if not idx or delta == 0:
            return idx
        if delta < 0:
            target = max(0, idx[0] + delta)
        else:
            target = min(len(self.pages), idx[-1] + 1 + delta)
        return self.move(idx, target)

    def delete(self, indices: Iterable[int]) -> list[int]:
        idx = _normalize(indices, len(self.pages))
        if not idx or len(idx) >= len(self.pages):
            return []  # never delete every page
        self._snapshot()
        drop = set(idx)
        self.pages = [p for i, p in enumerate(self.pages) if i not in drop]
        return [min(idx[0], len(self.pages) - 1)]

    def duplicate(self, indices: Iterable[int]) -> list[int]:
        idx = _normalize(indices, len(self.pages))
        if not idx:
            return []
        self._snapshot()
        copies = [copy.deepcopy(self.pages[i]) for i in idx]
        at = idx[-1] + 1
        self.pages[at:at] = copies
        return list(range(at, at + len(copies)))

    def insert_blank(self, at: int, count: int = 1) -> list[int]:
        at = max(0, min(len(self.pages), at))
        self._snapshot()
        self.pages[at:at] = [PageSpec(None) for _ in range(count)]
        return list(range(at, at + count))

    def rotate(self, indices: Iterable[int], degrees: int) -> list[int]:
        idx = _normalize(indices, len(self.pages))
        if not idx:
            return []
        self._snapshot()
        for i in idx:
            p = self.pages[i]
            self.pages[i] = replace(p, rotation=(p.rotation + degrees) % 360)
        return idx

    def update(self, indices: Iterable[int], **changes) -> list[int]:
        """Set adjustment fields (crop_mm, scale, offset_mm, rotation) on pages."""
        idx = _normalize(indices, len(self.pages))
        if not idx:
            return []
        if "scale" in changes:
            changes["scale"] = max(0.1, min(1.0, float(changes["scale"])))
        if "rotation" in changes:
            changes["rotation"] = int(changes["rotation"]) % 360
        self._snapshot()
        for i in idx:
            if not self.pages[i].is_blank:
                self.pages[i] = replace(self.pages[i], **changes)
        return idx

    def reset(self, indices: Iterable[int]) -> list[int]:
        idx = _normalize(indices, len(self.pages))
        if not idx:
            return []
        self._snapshot()
        for i in idx:
            self.pages[i] = self.pages[i].reset_adjustments()
        return idx

    def reverse(self, indices: Iterable[int]) -> list[int]:
        idx = _normalize(indices, len(self.pages))
        if len(idx) < 2:
            return idx
        self._snapshot()
        chosen = [self.pages[i] for i in idx][::-1]
        for i, p in zip(idx, chosen):
            self.pages[i] = p
        return idx

    def restore_original(self, count: int) -> None:
        self._snapshot()
        self.pages = [PageSpec(i) for i in range(count)]


def parse_page_list(text: str, count: int) -> list[PageSpec]:
    """Parse a page list such as ``"1-4, blank, 6, 5, 8-, 7:r90"``.

    Items are 1-based page numbers or ranges (``a-b``, ``a-``, ``-b``; a range
    may go backwards, e.g. ``8-5``), or ``b``/``blank`` for a blank page.
    A ``:r90``/``:r180``/``:r270`` suffix rotates the item clockwise.
    """
    specs: list[PageSpec] = []
    for raw in text.split(","):
        item = raw.strip().lower()
        if not item:
            continue
        rotation = 0
        if ":" in item:
            item, _, suffix = item.partition(":")
            if not suffix.startswith("r") or not suffix[1:].isdigit() or int(suffix[1:]) % 90:
                raise ValueError(f"Invalid rotation: {raw.strip()}")
            rotation = int(suffix[1:]) % 360
            item = item.strip()
        if item in ("b", "blank"):
            specs.append(PageSpec(None))
            continue
        if "-" in item:
            a, _, b = item.partition("-")
            start = int(a) if a.strip() else 1
            end = int(b) if b.strip() else count
            step = 1 if end >= start else -1
            numbers = list(range(start, end + step, step))
        else:
            numbers = [int(item)]
        for n in numbers:
            if not 1 <= n <= count:
                raise ValueError(f"Page {n} out of range (1-{count})")
            specs.append(PageSpec(n - 1, rotation=rotation))
    if not specs:
        raise ValueError("Empty page list")
    return specs
