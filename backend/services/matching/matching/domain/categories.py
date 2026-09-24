"""Port of ``src/domain/categories.ts``.

The table itself lives in ``cappy_common.categories`` because the catalog
validates listings against it too; this module keeps the domain package
reading like the frontend's.
"""

from __future__ import annotations

from cappy_common.categories import (
    CATEGORIES,
    GROUP_IDS,
    GROUPS,
    CategoryMeta,
    GroupMeta,
    categories_in,
    category,
    duration_label,
    mode_of,
)

__all__ = [
    "CATEGORIES",
    "GROUPS",
    "GROUP_IDS",
    "CategoryMeta",
    "GroupMeta",
    "categories_in",
    "category",
    "duration_label",
    "mode_of",
]
