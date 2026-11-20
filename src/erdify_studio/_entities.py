"""Layout keys and diagram groups of erdify's entities."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from erdify import EntityInfo, EnumInfo

from erdify_studio._config import GroupBy
from erdify_studio._errors import DuplicateKeyError, LayoutError
from erdify_studio._layout import DEFAULT_GROUP, OVERVIEW

_RESERVED = (OVERVIEW, DEFAULT_GROUP)


def entity_key(entity: EntityInfo) -> str:
    """Return the layout key of ``entity``: ``schema.table``, or ``table`` without a schema.

    The key is the table, not the class, so a renamed class keeps its position.
    """
    if entity.schema:
        return f"{entity.schema}.{entity.table_name}"
    return entity.table_name


def enum_key(enum: EnumInfo) -> str:
    """Return the layout key of ``enum``: ``enum:<name>``."""
    return f"enum:{enum.name}"


def entity_keys(entities: Mapping[str, EntityInfo]) -> dict[str, str]:
    """Map every entity name (erdify's key) to its layout key.

    The layout key is ``entity_key`` while no other entity has it. Entities that
    share one (same-name classes in different modules, which erdify names
    ``module.Class``; or several classes of one table) are keyed by their erdify
    name instead, so only they change key when a namesake appears.

    Raises:
        DuplicateKeyError: An erdify name used as a key equals another entity's key.
    """
    base = {name: entity_key(entity) for name, entity in entities.items()}
    shared = Counter(base.values())
    keys = {name: name if shared[key] > 1 else key for name, key in base.items()}
    owners: dict[str, str] = {}
    for name, key in keys.items():
        if key in owners:
            first, second = sorted((owners[key], name))
            raise DuplicateKeyError(
                f"entities {first!r} and {second!r} have the same layout key {key!r}"
            )
        owners[key] = name
    return keys


def entity_ids(entities: Mapping[str, EntityInfo]) -> dict[str, str]:
    """Map every entity name (``EntityInfo.name``) to its key in ``entities``.

    erdify's edges and ``enum_users`` name entities by ``EntityInfo.name``, which
    may differ from the dict key; a key equal to the name wins over another entity
    of that name.
    """
    ids = {name: name for name, entity in entities.items() if entity.name == name}
    for name, entity in sorted(entities.items()):
        ids.setdefault(entity.name, name)
    return ids


def entity_groups(entities: Mapping[str, EntityInfo], group_by: GroupBy) -> dict[str, str]:
    """Map every entity name to the group diagram it belongs to.

    ``auto`` decides per entity: its schema, else its Django app, else its module.
    An entity without a value goes to ``DEFAULT_GROUP``. ``none`` gives no groups
    (an empty mapping): the overview is the only diagram.

    Raises:
        LayoutError: A group value is a reserved diagram name.
    """
    if group_by == "none":
        return {}
    groups: dict[str, str] = {}
    for name, entity in entities.items():
        group = _group_value(entity, group_by)
        if group in _RESERVED:
            raise LayoutError(
                f"group {group!r} is a reserved diagram name (entity {name!r}); "
                f"set [tool.erdify-studio] group_by to another value"
            )
        groups[name] = group or DEFAULT_GROUP
    return groups


def _group_value(entity: EntityInfo, group_by: GroupBy) -> str | None:
    if group_by == "schema":
        return entity.schema
    if group_by == "app":
        return entity.app
    if group_by == "module":
        return entity.module
    return entity.schema or entity.app or entity.module
