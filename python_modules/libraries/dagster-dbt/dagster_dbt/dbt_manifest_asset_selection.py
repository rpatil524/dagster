from collections.abc import Mapping
from typing import AbstractSet, Any, Optional  # noqa: UP035

from dagster import (
    AssetKey,
    AssetSelection,
    _check as check,
)
from dagster._core.definitions.asset_checks.asset_check_spec import AssetCheckKey
from dagster._core.definitions.assets.graph.base_asset_graph import BaseAssetGraph
from dagster._record import record

from dagster_dbt.asset_utils import (
    DBT_DEFAULT_EXCLUDE,
    DBT_DEFAULT_SELECT,
    DBT_DEFAULT_SELECTOR,
    get_asset_check_key_for_test,
    get_node,
    is_non_asset_node,
)
from dagster_dbt.dagster_dbt_translator import DagsterDbtTranslator
from dagster_dbt.dbt_manifest import DbtManifestParam, validate_manifest
from dagster_dbt.utils import ASSET_RESOURCE_TYPES, select_unique_ids_from_manifest


@record
class DbtManifestAssetSelection(AssetSelection):
    """Defines a selection of assets from a dbt manifest wrapper and a dbt selection string.

    Args:
        manifest (Mapping[str, Any]): The dbt manifest blob.
        select (str): A dbt selection string to specify a set of dbt resources.
        exclude (Optional[str]): A dbt selection string to exclude a set of dbt resources.

    Examples:
        .. code-block:: python

            import json
            from pathlib import Path

            from dagster_dbt import DbtManifestAssetSelection

            manifest = json.loads(Path("path/to/manifest.json").read_text())

            # select the dbt assets that have the tag "foo".
            my_selection = DbtManifestAssetSelection(manifest=manifest, select="tag:foo")
    """

    manifest: Mapping[str, Any]
    select: str
    dagster_dbt_translator: DagsterDbtTranslator
    exclude: str
    selector: str

    def __eq__(self, other):
        if not isinstance(other, DbtManifestAssetSelection):
            return False

        self_metadata = self.manifest.get("metadata")
        other_metadata = other.manifest.get("metadata")

        if not self_metadata or not other_metadata:
            return super().__eq__(other)

        # Compare metadata only since it uniquely identifies the manifest and the
        # full manifest dictionary can be large
        return (
            self_metadata == other_metadata
            and self.select == other.select
            and self.dagster_dbt_translator == other.dagster_dbt_translator
            and self.exclude == other.exclude
            and self.selector == other.selector
        )

    @classmethod
    def build(
        cls,
        manifest: DbtManifestParam,
        select: str = DBT_DEFAULT_SELECT,
        *,
        dagster_dbt_translator: Optional[DagsterDbtTranslator] = None,
        exclude: str = DBT_DEFAULT_EXCLUDE,
        selector: str = DBT_DEFAULT_SELECTOR,
    ):
        return cls(
            manifest=validate_manifest(manifest),
            select=check.str_param(select, "select"),
            dagster_dbt_translator=check.opt_inst_param(
                dagster_dbt_translator,
                "dagster_dbt_translator",
                DagsterDbtTranslator,
                DagsterDbtTranslator(),
            ),
            exclude=check.str_param(exclude, "exclude"),
            selector=check.str_param(selector, "selector"),
        )

    def resolve_inner(
        self, asset_graph: BaseAssetGraph, allow_missing: bool = False
    ) -> AbstractSet[AssetKey]:
        keys = set()
        for unique_id in select_unique_ids_from_manifest(
            select=self.select,
            exclude=self.exclude,
            selector=self.selector,
            manifest_json=self.manifest,
        ):
            dbt_resource_props = get_node(self.manifest, unique_id)
            is_dbt_asset = dbt_resource_props["resource_type"] in ASSET_RESOURCE_TYPES
            if is_dbt_asset and not is_non_asset_node(dbt_resource_props):
                asset_key = self.dagster_dbt_translator.get_asset_spec(
                    self.manifest, unique_id, None
                ).key
                keys.add(asset_key)

        return keys

    def resolve_checks_inner(
        self, asset_graph: BaseAssetGraph, allow_missing: bool
    ) -> AbstractSet[AssetCheckKey]:
        if not self.dagster_dbt_translator.settings.enable_asset_checks:
            return set()

        keys = set()
        for unique_id in select_unique_ids_from_manifest(
            select=self.select,
            exclude=self.exclude,
            selector=self.selector,
            manifest_json=self.manifest,
        ):
            asset_check_key = get_asset_check_key_for_test(
                self.manifest,
                self.dagster_dbt_translator,
                test_unique_id=unique_id,
                project=None,
            )

            if asset_check_key:
                keys.add(asset_check_key)

        return keys
