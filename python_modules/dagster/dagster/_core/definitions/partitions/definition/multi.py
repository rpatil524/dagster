import hashlib
import itertools
from collections.abc import Mapping, Sequence
from datetime import datetime
from functools import lru_cache, reduce
from typing import TYPE_CHECKING, Optional, Union, cast

from dagster_shared.check.functions import CheckError

import dagster._check as check
from dagster._annotations import public
from dagster._core.definitions.partitions.context import (
    PartitionLoadingContext,
    partition_loading_context,
)
from dagster._core.definitions.partitions.definition.dynamic import DynamicPartitionsDefinition
from dagster._core.definitions.partitions.definition.partitions_definition import (
    PartitionsDefinition,
)
from dagster._core.definitions.partitions.definition.static import StaticPartitionsDefinition
from dagster._core.definitions.partitions.definition.time_window import (
    TimeWindowPartitionsDefinition,
)
from dagster._core.definitions.partitions.partition_key_range import PartitionKeyRange
from dagster._core.definitions.partitions.subset.default import DefaultPartitionsSubset
from dagster._core.definitions.partitions.utils.multi import (
    INVALID_STATIC_PARTITIONS_KEY_CHARACTERS,
    MULTIPARTITION_KEY_DELIMITER,
    MultiDimensionalPartitionKeyIterator,
    MultiPartitionCursor,
    MultiPartitionKey,
    PartitionDimensionDefinition,
    get_tags_from_multi_partition_key,
)
from dagster._core.definitions.partitions.utils.time_window import TimeWindow
from dagster._core.errors import (
    DagsterInvalidDefinitionError,
    DagsterInvalidInvocationError,
    DagsterUnknownPartitionError,
)
from dagster._core.instance import DynamicPartitionsStore
from dagster._core.types.pagination import PaginatedResults

if TYPE_CHECKING:
    from dagster._core.definitions.partitions.subset.partitions_subset import PartitionsSubset

ALLOWED_PARTITION_DIMENSION_TYPES = (
    StaticPartitionsDefinition,
    TimeWindowPartitionsDefinition,
    DynamicPartitionsDefinition,
)


def _check_valid_partitions_dimensions(
    partitions_dimensions: Mapping[str, PartitionsDefinition],
) -> None:
    for dim_name, partitions_def in partitions_dimensions.items():
        if not any(isinstance(partitions_def, t) for t in ALLOWED_PARTITION_DIMENSION_TYPES):
            raise DagsterInvalidDefinitionError(
                f"Invalid partitions definition type {type(partitions_def)}. "
                "Only the following partitions definition types are supported: "
                f"{ALLOWED_PARTITION_DIMENSION_TYPES}."
            )
        if isinstance(partitions_def, DynamicPartitionsDefinition) and partitions_def.name is None:
            raise DagsterInvalidDefinitionError(
                "DynamicPartitionsDefinition must have a name to be used in a"
                " MultiPartitionsDefinition."
            )

        if isinstance(partitions_def, StaticPartitionsDefinition):
            if any(
                [
                    INVALID_STATIC_PARTITIONS_KEY_CHARACTERS & set(key)
                    for key in partitions_def.get_partition_keys()
                ]
            ):
                raise DagsterInvalidDefinitionError(
                    f"Invalid character in partition key for dimension {dim_name}. "
                    "A multi-partitions definition cannot contain partition keys with "
                    "the following characters: |, [, ], ,"
                )


@public
class MultiPartitionsDefinition(PartitionsDefinition[MultiPartitionKey]):
    """Takes the cross-product of partitions from two partitions definitions.

    For example, with a static partitions definition where the partitions are ["a", "b", "c"]
    and a daily partitions definition, this partitions definition will have the following
    partitions:

    2020-01-01|a
    2020-01-01|b
    2020-01-01|c
    2020-01-02|a
    2020-01-02|b
    ...

    We recommended limiting partition counts for each asset to 100,000 partitions or fewer.

    Args:
        partitions_defs (Mapping[str, PartitionsDefinition]):
            A mapping of dimension name to partitions definition. The total set of partitions will
            be the cross-product of the partitions from each PartitionsDefinition.

    Args:
        partitions_defs (Sequence[PartitionDimensionDefinition]):
            A sequence of PartitionDimensionDefinition objects, each of which contains a dimension
            name and a PartitionsDefinition. The total set of partitions will be the cross-product
            of the partitions from each PartitionsDefinition. This sequence is ordered by
            dimension name, to ensure consistent ordering of the partitions.
    """

    def __init__(self, partitions_defs: Mapping[str, PartitionsDefinition]):
        if not len(partitions_defs.keys()) == 2:
            raise DagsterInvalidInvocationError(
                "Dagster currently only supports multi-partitions definitions with 2 partitions"
                " definitions. Your multi-partitions definition has"
                f" {len(partitions_defs.keys())} partitions definitions."
            )
        check.mapping_param(
            partitions_defs, "partitions_defs", key_type=str, value_type=PartitionsDefinition
        )

        _check_valid_partitions_dimensions(partitions_defs)

        self._partitions_defs: list[PartitionDimensionDefinition] = sorted(
            [
                PartitionDimensionDefinition(name, partitions_def)
                for name, partitions_def in partitions_defs.items()
            ],
            key=lambda x: x.name,
        )

    @property
    def partitions_subset_class(self) -> type["PartitionsSubset"]:
        return DefaultPartitionsSubset

    def get_partition_keys_in_range(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        partition_key_range: PartitionKeyRange,
        dynamic_partitions_store: Optional[DynamicPartitionsStore] = None,
    ) -> Sequence[str]:
        with partition_loading_context(dynamic_partitions_store=dynamic_partitions_store):
            start: MultiPartitionKey = self.get_partition_key_from_str(partition_key_range.start)
            end: MultiPartitionKey = self.get_partition_key_from_str(partition_key_range.end)

            partition_key_sequences = [
                partition_dim.partitions_def.get_partition_keys_in_range(
                    PartitionKeyRange(
                        start.keys_by_dimension[partition_dim.name],
                        end.keys_by_dimension[partition_dim.name],
                    ),
                )
                for partition_dim in self._partitions_defs
            ]

            return [
                MultiPartitionKey(
                    {
                        self._partitions_defs[i].name: key
                        for i, key in enumerate(partition_key_tuple)
                    }
                )
                for partition_key_tuple in itertools.product(*partition_key_sequences)
            ]

    def get_serializable_unique_identifier(self) -> str:
        return hashlib.sha1(
            str(
                {
                    dim_def.name: dim_def.partitions_def.get_serializable_unique_identifier()
                    for dim_def in self.partitions_defs
                }
            ).encode("utf-8")
        ).hexdigest()

    @property
    def partition_dimension_names(self) -> list[str]:
        return [dim_def.name for dim_def in self._partitions_defs]

    @property
    def partitions_defs(self) -> Sequence[PartitionDimensionDefinition]:
        return self._partitions_defs

    def get_partitions_def_for_dimension(self, dimension_name: str) -> PartitionsDefinition:
        for dim_def in self._partitions_defs:
            if dim_def.name == dimension_name:
                return dim_def.partitions_def
        check.failed(f"Invalid dimension name {dimension_name}")

    # We override the default implementation of `has_partition_key` for performance.
    def has_partition_key(self, partition_key: Union[MultiPartitionKey, str]) -> bool:
        if isinstance(partition_key, str):
            try:
                partition_key = self.get_partition_key_from_str(partition_key)
            except CheckError:
                return False

        if partition_key.keys_by_dimension.keys() != set(self.partition_dimension_names):
            raise DagsterUnknownPartitionError(
                f"Invalid partition key {partition_key}. The dimensions of the partition key are"
                " not the dimensions of the partitions definition."
            )

        for dimension in self.partitions_defs:
            if not dimension.partitions_def.has_partition_key(
                partition_key.keys_by_dimension[dimension.name]
            ):
                return False
        return True

    # store results for repeated calls with the same current_time
    @lru_cache(maxsize=1)
    def _get_partition_keys(self, _current_time: datetime) -> Sequence[MultiPartitionKey]:
        partition_key_sequences = [
            partition_dim.partitions_def.get_partition_keys()
            for partition_dim in self._partitions_defs
        ]

        keys = [
            MultiPartitionKey(
                {self._partitions_defs[i].name: key for i, key in enumerate(partition_key_tuple)}
            )
            for partition_key_tuple in itertools.product(*partition_key_sequences)
        ]
        # in some cases, an underlying partitions definition may have keys in a format
        # that produce invalid multi-partition keys (e.g. they have a | character).
        # in these cases, we filter out the invalid keys.
        return [key for key in keys if self._is_valid_key_format(key)]

    @public
    def get_partition_keys(
        self,
        current_time: Optional[datetime] = None,
        dynamic_partitions_store: Optional[DynamicPartitionsStore] = None,
    ) -> Sequence[MultiPartitionKey]:
        """Returns a list of MultiPartitionKeys representing the partition keys of the
        PartitionsDefinition.

        Args:
            current_time (Optional[datetime]): A datetime object representing the current time, only
                applicable to time-based partition dimensions.
            dynamic_partitions_store (Optional[DynamicPartitionsStore]): The DynamicPartitionsStore
                object that is responsible for fetching dynamic partitions. Required when a
                dimension is a DynamicPartitionsDefinition with a name defined. Users can pass the
                DagsterInstance fetched via `context.instance` to this argument.

        Returns:
            Sequence[MultiPartitionKey]
        """
        with partition_loading_context(current_time, dynamic_partitions_store) as ctx:
            return self._get_partition_keys(_current_time=ctx.effective_dt)

    def get_paginated_partition_keys(
        self,
        context: PartitionLoadingContext,
        limit: int,
        ascending: bool,
        cursor: Optional[str] = None,
    ) -> PaginatedResults[str]:
        """Returns a connection object that contains a list of partition keys and all the necessary
        information to paginate through them.

        Args:
            cursor: (Optional[str]): A cursor to track the progress paginating through the returned partition key results.
            limit: (Optional[int]): The maximum number of partition keys to return.

        Returns:
            PaginatedResults[MultiPartitionKey]
        """
        with partition_loading_context(new_ctx=context) as ctx:
            partition_keys = []
            iterator = MultiDimensionalPartitionKeyIterator(
                context=ctx,
                partition_defs=self._partitions_defs,
                cursor=MultiPartitionCursor.from_cursor(cursor),
                ascending=ascending,
            )
            next_cursor = cursor
            while iterator.has_next():
                partition_key = next(iterator)
                if not partition_key:
                    break

                partition_keys.append(partition_key)
                next_cursor = iterator.cursor().to_string()
                if len(partition_keys) >= limit:
                    break

            if not next_cursor:
                next_cursor = MultiPartitionCursor(last_seen_key=None).to_string()

            return PaginatedResults(
                results=partition_keys, cursor=next_cursor, has_more=iterator.has_next()
            )

    def _is_valid_key_format(self, partition_key: str) -> bool:
        """Checks if the given partition key is in the correct format for a multi-partition key
        of this MultiPartitionsDefinition.
        """
        return len(partition_key.split(MULTIPARTITION_KEY_DELIMITER)) == len(self.partitions_defs)

    def filter_valid_partition_keys(self, partition_keys: set[str]) -> set[MultiPartitionKey]:
        partition_keys_by_dimension = {
            dim.name: dim.partitions_def.get_partition_keys() for dim in self.partitions_defs
        }
        validated_partitions = set()
        for partition_key in partition_keys:
            if not self._is_valid_key_format(partition_key):
                continue

            partition_key_strs = partition_key.split(MULTIPARTITION_KEY_DELIMITER)
            multipartition_key = MultiPartitionKey(
                {dim.name: partition_key_strs[i] for i, dim in enumerate(self._partitions_defs)}
            )

            if all(
                key in partition_keys_by_dimension.get(dim, [])
                for dim, key in multipartition_key.keys_by_dimension.items()
            ):
                validated_partitions.add(partition_key)

        return validated_partitions

    def __eq__(self, other):
        return (
            isinstance(other, MultiPartitionsDefinition)
            and self.partitions_defs == other.partitions_defs
        )

    def __hash__(self):
        return hash(
            tuple(
                [
                    (partitions_def.name, partitions_def.__repr__())
                    for partitions_def in self.partitions_defs
                ]
            )
        )

    def __str__(self) -> str:
        dimension_1 = self._partitions_defs[0]
        dimension_2 = self._partitions_defs[1]
        partition_str = (
            "Multi-partitioned, with dimensions: \n"
            f"{dimension_1.name.capitalize()}: {dimension_1.partitions_def} \n"
            f"{dimension_2.name.capitalize()}: {dimension_2.partitions_def}"
        )
        return partition_str

    def __repr__(self) -> str:
        return f"{type(self).__name__}(dimensions={[str(dim) for dim in self.partitions_defs]}"

    def get_partition_key_from_str(self, partition_key_str: str) -> MultiPartitionKey:
        """Given a string representation of a partition key, returns a MultiPartitionKey object."""
        check.str_param(partition_key_str, "partition_key_str")

        partition_key_strs = partition_key_str.split(MULTIPARTITION_KEY_DELIMITER)
        check.invariant(
            len(partition_key_strs) == len(self.partitions_defs),
            f"Expected {len(self.partitions_defs)} partition keys in partition key string"
            f" {partition_key_str}, but got {len(partition_key_strs)}",
        )

        return MultiPartitionKey(
            {dim.name: partition_key_strs[i] for i, dim in enumerate(self._partitions_defs)}
        )

    def _get_primary_and_secondary_dimension(
        self,
    ) -> tuple[PartitionDimensionDefinition, PartitionDimensionDefinition]:
        # Multipartitions subsets are serialized by primary dimension. If changing
        # the selection of primary/secondary dimension, will need to also update the
        # serialization of MultiPartitionsSubsets

        time_dimensions = self._get_time_window_dims()
        if len(time_dimensions) == 1:
            primary_dimension, secondary_dimension = (
                time_dimensions[0],
                next(iter([dim for dim in self.partitions_defs if dim != time_dimensions[0]])),
            )
        else:
            primary_dimension, secondary_dimension = (
                self.partitions_defs[0],
                self.partitions_defs[1],
            )

        return primary_dimension, secondary_dimension

    @property
    def primary_dimension(self) -> PartitionDimensionDefinition:
        return self._get_primary_and_secondary_dimension()[0]

    @property
    def secondary_dimension(self) -> PartitionDimensionDefinition:
        return self._get_primary_and_secondary_dimension()[1]

    def get_tags_for_partition_key(self, partition_key: str) -> Mapping[str, str]:
        partition_key = cast("MultiPartitionKey", self.get_partition_key_from_str(partition_key))
        tags = {**super().get_tags_for_partition_key(partition_key)}
        tags.update(get_tags_from_multi_partition_key(partition_key))
        return tags

    @property
    def time_window_dimension(self) -> PartitionDimensionDefinition:
        time_window_dims = self._get_time_window_dims()
        check.invariant(
            len(time_window_dims) == 1, "Expected exactly one time window partitioned dimension"
        )
        return next(iter(time_window_dims))

    def _get_time_window_dims(self) -> list[PartitionDimensionDefinition]:
        return [
            dim
            for dim in self.partitions_defs
            if isinstance(dim.partitions_def, TimeWindowPartitionsDefinition)
        ]

    @property
    def has_time_window_dimension(self) -> bool:
        return bool(self._get_time_window_dims())

    @property
    def time_window_partitions_def(self) -> TimeWindowPartitionsDefinition:
        check.invariant(self.has_time_window_dimension, "Must have time window dimension")
        return cast(
            "TimeWindowPartitionsDefinition",
            check.inst(self.primary_dimension.partitions_def, TimeWindowPartitionsDefinition),
        )

    def time_window_for_partition_key(self, partition_key: str) -> TimeWindow:
        if not isinstance(partition_key, MultiPartitionKey):
            partition_key = self.get_partition_key_from_str(partition_key)

        time_window_dimension = self.time_window_dimension
        return cast(
            "TimeWindowPartitionsDefinition", time_window_dimension.partitions_def
        ).time_window_for_partition_key(
            cast("MultiPartitionKey", partition_key).keys_by_dimension[time_window_dimension.name]
        )

    def get_multipartition_keys_with_dimension_value(
        self, dimension_name: str, dimension_partition_key: str
    ) -> Sequence[MultiPartitionKey]:
        check.str_param(dimension_name, "dimension_name")
        check.str_param(dimension_partition_key, "dimension_partition_key")

        matching_dimensions = [
            dimension for dimension in self.partitions_defs if dimension.name == dimension_name
        ]
        other_dimensions = [
            dimension for dimension in self.partitions_defs if dimension.name != dimension_name
        ]

        check.invariant(
            len(matching_dimensions) == 1,
            f"Dimension {dimension_name} not found in MultiPartitionsDefinition with dimensions"
            f" {[dim.name for dim in self.partitions_defs]}",
        )

        partition_sequences = [
            partition_dim.partitions_def.get_partition_keys() for partition_dim in other_dimensions
        ] + [[dimension_partition_key]]

        # Names of partitions dimensions in the same order as partition_sequences
        partition_dim_names = [dim.name for dim in other_dimensions] + [dimension_name]

        return [
            MultiPartitionKey(
                {
                    partition_dim_names[i]: partition_key
                    for i, partition_key in enumerate(partitions_tuple)
                }
            )
            for partitions_tuple in itertools.product(*partition_sequences)
        ]

    def get_num_partitions(self) -> int:
        # Static partitions definitions can contain duplicate keys (will throw error in 1.3.0)
        # In the meantime, relying on get_num_partitions to handle duplicates to display
        # correct counts in the Dagster UI.
        dimension_counts = [dim.partitions_def.get_num_partitions() for dim in self.partitions_defs]
        return reduce(lambda x, y: x * y, dimension_counts, 1)
