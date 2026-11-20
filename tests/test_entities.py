import pytest
from erdify import EntityInfo, EnumInfo

from erdify_studio import (
    DEFAULT_GROUP,
    OVERVIEW,
    DuplicateKeyError,
    LayoutError,
    entity_groups,
    entity_keys,
    enum_key,
)


def _entity(
    name: str,
    table: str,
    *,
    schema: str | None = None,
    module: str | None = None,
    app: str | None = None,
) -> EntityInfo:
    return EntityInfo(name=name, table_name=table, schema=schema, module=module, app=app)


def test_keys_are_schema_dot_table_or_table() -> None:
    entities = {
        "Customer": _entity("Customer", "customers", schema="core"),
        "Order": _entity("Order", "order", module="shop.models"),
        "CUSTOMER": _entity("CUSTOMER", "CUSTOMER", schema="MART"),
    }
    assert entity_keys(entities) == {
        "Customer": "core.customers",
        "Order": "order",
        "CUSTOMER": "MART.CUSTOMER",
    }


def test_key_survives_a_class_rename() -> None:
    before = entity_keys({"Customer": _entity("Customer", "customers", schema="core")})
    after = entity_keys({"Client": _entity("Client", "customers", schema="core")})
    assert list(before.values()) == list(after.values())


def test_enum_key() -> None:
    assert enum_key(EnumInfo(name="Status", values=["a"])) == "enum:Status"


def test_two_entities_with_the_same_key_are_an_error_naming_both() -> None:
    entities = {
        "Address": _entity("Address", "address", module="billing.models"),
        "ShippingAddress": _entity("ShippingAddress", "address", module="shipping.models"),
    }
    with pytest.raises(DuplicateKeyError, match=r"'Address' and 'ShippingAddress'.*'address'"):
        entity_keys(entities)


def test_duplicate_key_error_is_a_layout_error() -> None:
    assert issubclass(DuplicateKeyError, LayoutError)


ENTITIES = {
    "Customer": _entity("Customer", "customers", schema="core", module="shop.models"),
    "Order": _entity("Order", "order", module="shop.models"),
    "Book": _entity("Book", "library_book", module="library.models", app="library"),
    "audit": _entity("audit", "audit"),
}


@pytest.mark.parametrize(
    ("group_by", "expected"),
    [
        (
            "auto",
            {"Customer": "core", "Order": "shop.models", "Book": "library", "audit": DEFAULT_GROUP},
        ),
        (
            "schema",
            {
                "Customer": "core",
                "Order": DEFAULT_GROUP,
                "Book": DEFAULT_GROUP,
                "audit": DEFAULT_GROUP,
            },
        ),
        (
            "app",
            {
                "Customer": DEFAULT_GROUP,
                "Order": DEFAULT_GROUP,
                "Book": "library",
                "audit": DEFAULT_GROUP,
            },
        ),
        (
            "module",
            {
                "Customer": "shop.models",
                "Order": "shop.models",
                "Book": "library.models",
                "audit": DEFAULT_GROUP,
            },
        ),
        ("none", {}),
    ],
)
def test_groups(group_by: str, expected: dict[str, str]) -> None:
    assert entity_groups(ENTITIES, group_by) == expected  # type: ignore[arg-type]


def test_auto_prefers_schema_over_app_and_module() -> None:
    entity = _entity("T", "t", schema="core", module="m", app="a")
    assert entity_groups({"T": entity}, "auto") == {"T": "core"}


def test_auto_prefers_app_over_module() -> None:
    entity = _entity("T", "t", module="m", app="a")
    assert entity_groups({"T": entity}, "auto") == {"T": "a"}


@pytest.mark.parametrize("reserved", [OVERVIEW, DEFAULT_GROUP])
@pytest.mark.parametrize(
    ("group_by", "source"),
    [("schema", "schema"), ("app", "app"), ("module", "module"), ("auto", "schema")],
)
def test_a_group_named_like_a_reserved_diagram_is_an_error(
    reserved: str, group_by: str, source: str
) -> None:
    entity = _entity("T", "t", **{source: reserved})
    with pytest.raises(LayoutError, match=rf"'{reserved}'.*reserved.*'T'"):
        entity_groups({"T": entity}, group_by)  # type: ignore[arg-type]
