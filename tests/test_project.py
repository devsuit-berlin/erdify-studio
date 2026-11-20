"""End to end with erdify's real parser: config, keys and groups for a project."""

from pathlib import Path

import erdify

from erdify_studio import (
    OVERVIEW,
    Layout,
    entity_groups,
    entity_keys,
    load_config,
    load_layout,
    save_layout,
)

MODELS = """\
from sqlmodel import Field, SQLModel


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    __table_args__ = {"schema": "core"}
    id: int = Field(primary_key=True)


class Order(SQLModel, table=True):
    id: int = Field(primary_key=True)
    customer_id: int = Field(foreign_key="core.customers.id")
"""


def test_layout_for_a_parsed_project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.erdify]\ninclude = ["**/models.py"]\n\n'
        '[tool.erdify-studio]\nlayout = "docs/erdify-layout.json"\n'
    )
    package = tmp_path / "src" / "shop"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(MODELS)

    # Studio reads the pyproject.toml erdify resolved, from a nested input path too.
    project = erdify.load_project(tmp_path / "src")
    config = load_config(project.settings.pyproject)
    assert config.layout == tmp_path / "docs" / "erdify-layout.json"

    keys = entity_keys(project.entities)
    assert keys == {"Customer": "core.customers", "Order": "order"}
    assert entity_groups(project.entities, config.group_by) == {
        "Customer": "core",
        "Order": "shop.models",
    }

    layout = Layout()
    for i, key in enumerate(sorted(keys.values())):
        layout.set_position(OVERVIEW, key, i * 300, 0)
    save_layout(layout, config.layout)
    assert load_layout(config.layout) == layout
