import dagster as dg
import pytest
from dagster import AssetExecutionContext, ResourceDefinition


def test_basic_materialize_to_memory():
    @dg.asset
    def the_asset():
        return 5

    result = dg.materialize_to_memory([the_asset])
    assert result.success
    assert len(result.asset_materializations_for_node("the_asset")[0].metadata) == 0
    assert result.asset_value(the_asset.key) == 5


def test_materialize_config():
    @dg.asset(config_schema={"foo_str": str})
    def the_asset_reqs_config(context):
        assert context.op_execution_context.op_config["foo_str"] == "foo"

    assert dg.materialize_to_memory(
        [the_asset_reqs_config],
        run_config={"ops": {"the_asset_reqs_config": {"config": {"foo_str": "foo"}}}},
    ).success


def test_materialize_bad_config():
    @dg.asset(config_schema={"foo_str": str})
    def the_asset_reqs_config(context):
        assert context.op_execution_context.op_config["foo_str"] == "foo"

    with pytest.raises(dg.DagsterInvalidConfigError, match="Error in config for job"):
        dg.materialize_to_memory(
            [the_asset_reqs_config],
            run_config={"ops": {"the_asset_reqs_config": {"config": {"bad": "foo"}}}},
        )


def test_materialize_resources():
    @dg.asset(resource_defs={"foo": ResourceDefinition.hardcoded_resource("blah")})
    def the_asset(context):
        assert context.resources.foo == "blah"

    assert dg.materialize_to_memory([the_asset]).success


def test_materialize_resource_instances():
    @dg.asset(required_resource_keys={"foo", "bar"})
    def the_asset(context):
        assert context.resources.foo == "blah"
        assert context.resources.bar == "baz"

    assert dg.materialize_to_memory(
        [the_asset], resources={"foo": ResourceDefinition.hardcoded_resource("blah"), "bar": "baz"}
    ).success


def test_materialize_resources_not_satisfied():
    @dg.asset(required_resource_keys={"foo"})
    def the_asset(context):
        assert context.resources.foo == "blah"

    with pytest.raises(
        dg.DagsterInvalidDefinitionError,
        match="resource with key 'foo' required by op 'the_asset' was not provided",
    ):
        dg.materialize_to_memory([the_asset])

    with pytest.raises(
        dg.DagsterInvariantViolationError,
        match=(
            "Attempted to call `materialize_to_memory` with a resource provided for io manager key"
            " 'io_manager'. Do not provide resources for io manager keys when calling"
            " `materialize_to_memory`, as it will override io management behavior for all keys."
        ),
    ):
        dg.materialize_to_memory(
            dg.with_resources([the_asset], {"foo": ResourceDefinition.hardcoded_resource("blah")})
        )


def test_materialize_conflicting_resources():
    @dg.asset(resource_defs={"foo": ResourceDefinition.hardcoded_resource("1")})
    def first():
        pass

    @dg.asset(resource_defs={"foo": ResourceDefinition.hardcoded_resource("2")})
    def second():
        pass

    with pytest.raises(
        dg.DagsterInvalidDefinitionError,
        match="Conflicting versions of resource with key 'foo' were provided to different assets.",
    ):
        dg.materialize_to_memory([first, second])

    with pytest.raises(
        dg.DagsterInvalidInvocationError,
        match=(
            r'AssetsDefinition with key \["first"\] has conflicting resource definitions with'
            r" provided resources for the following keys: foo. Either remove the existing"
            r" resources from the asset or change the resource keys"
        ),
    ):
        dg.materialize_to_memory(
            [first], resources={"foo": ResourceDefinition.hardcoded_resource("2")}
        )


def test_materialize_source_assets():
    class MyIOManager(dg.IOManager):
        def handle_output(self, context, obj):
            pass

        def load_input(self, context):
            return 5

    @dg.io_manager
    def the_manager():
        return MyIOManager()

    the_source = dg.SourceAsset(key=dg.AssetKey(["the_source"]), io_manager_def=the_manager)

    @dg.asset
    def the_asset(the_source):
        return the_source + 1

    with pytest.raises(
        dg.DagsterInvariantViolationError,
        match=(
            "Attempted to call `materialize_to_memory` with a resource "
            "provided for io manager key 'the_source__io_manager'. Do not provide "
            "resources for io manager keys when calling `materialize_to_memory`, as "
            "it will override io management behavior for all keys."
        ),
    ):
        dg.materialize_to_memory([the_asset, the_source])


def test_materialize_no_assets():
    assert dg.materialize_to_memory([]).success


def test_materialize_graph_backed_asset():
    @dg.asset
    def a():
        return "a"

    @dg.asset
    def b():
        return "b"

    @dg.op
    def double_string(s):
        return s * 2

    @dg.op
    def combine_strings(s1, s2):
        return s1 + s2

    @dg.graph
    def create_cool_thing(a, b):
        da = double_string(double_string(a))
        db = double_string(b)
        return combine_strings(da, db)

    cool_thing_asset = dg.AssetsDefinition(
        keys_by_input_name={"a": dg.AssetKey("a"), "b": dg.AssetKey("b")},
        keys_by_output_name={"result": dg.AssetKey("cool_thing")},
        node_def=create_cool_thing,
    )

    result = dg.materialize_to_memory([cool_thing_asset, a, b])
    assert result.success
    assert result.output_for_node("create_cool_thing.combine_strings") == "aaaabb"
    assert result.asset_value("cool_thing") == "aaaabb"


def test_materialize_multi_asset():
    @dg.op
    def upstream_op():
        return "foo"

    @dg.op(out={"o1": dg.Out(), "o2": dg.Out()})
    def two_outputs(upstream_op):
        o1 = upstream_op
        o2 = o1 + "bar"
        return o1, o2

    @dg.graph(out={"o1": dg.GraphOut(), "o2": dg.GraphOut()})
    def thing():
        o1, o2 = two_outputs(upstream_op())
        return (o1, o2)

    thing_asset = dg.AssetsDefinition(
        keys_by_input_name={},
        keys_by_output_name={"o1": dg.AssetKey("thing"), "o2": dg.AssetKey("thing_2")},
        node_def=thing,
        asset_deps={dg.AssetKey("thing"): set(), dg.AssetKey("thing_2"): {dg.AssetKey("thing")}},
    )

    @dg.multi_asset(
        outs={
            "my_out_name": dg.AssetOut(metadata={"foo": "bar"}),
            "my_other_out_name": dg.AssetOut(metadata={"bar": "foo"}),
        },
        internal_asset_deps={
            "my_out_name": {dg.AssetKey("my_other_out_name")},
            "my_other_out_name": {dg.AssetKey("thing")},
        },
    )
    def multi_asset_with_internal_deps(thing):
        yield dg.Output(2, "my_other_out_name")
        yield dg.Output(1, "my_out_name")

    result = dg.materialize_to_memory([thing_asset, multi_asset_with_internal_deps])
    assert result.success
    assert result.output_for_node("multi_asset_with_internal_deps", "my_out_name") == 1
    assert result.output_for_node("multi_asset_with_internal_deps", "my_other_out_name") == 2


def test_materialize_to_memory_partition_key():
    @dg.asset(partitions_def=dg.DailyPartitionsDefinition(start_date="2022-01-01"))
    def the_asset(context: AssetExecutionContext):
        assert context.partition_key == "2022-02-02"

    result = dg.materialize_to_memory([the_asset], partition_key="2022-02-02")
    assert result.success


def test_materialize_tags():
    @dg.asset
    def the_asset(context: AssetExecutionContext):
        assert context.run.tags.get("key1") == "value1"

    result = dg.materialize_to_memory([the_asset], tags={"key1": "value1"})
    assert result.success
    assert result.dagster_run.tags == {"key1": "value1"}


def test_materialize_to_memory_partition_key_and_run_config():
    @dg.asset(config_schema={"value": str})
    def configurable(context):
        assert context.op_execution_context.op_config["value"] == "a"

    @dg.asset(partitions_def=dg.DailyPartitionsDefinition(start_date="2022-09-11"))
    def partitioned(context):
        assert context.partition_key == "2022-09-11"

    assert dg.materialize_to_memory(
        [partitioned, configurable],
        partition_key="2022-09-11",
        run_config={"ops": {"configurable": {"config": {"value": "a"}}}},
    ).success


def test_materialize_to_memory_provided_io_manager_instance():
    @dg.io_manager  # pyright: ignore[reportCallIssue,reportArgumentType]
    def the_manager():
        pass

    @dg.asset(io_manager_key="blah")
    def the_asset():
        pass

    with pytest.raises(
        dg.DagsterInvariantViolationError,
        match=(
            "Attempted to call `materialize_to_memory` with a resource "
            "provided for io manager key 'blah'. Do not provide resources for io "
            "manager keys when calling `materialize_to_memory`, as it will override "
            "io management behavior for all keys."
        ),
    ):
        dg.materialize_to_memory([the_asset], resources={"blah": the_manager})

    class MyIOManager(dg.IOManager):
        def handle_output(self, context, obj):
            pass

        def load_input(self, context):
            pass

    with pytest.raises(
        dg.DagsterInvariantViolationError,
        match=(
            "Attempted to call `materialize_to_memory` with a resource "
            "provided for io manager key 'blah'. Do not provide resources for io "
            "manager keys when calling `materialize_to_memory`, as it will override "
            "io management behavior for all keys."
        ),
    ):
        dg.materialize_to_memory([the_asset], resources={"blah": MyIOManager()})


def test_raise_on_error():
    @dg.asset
    def asset1():
        raise ValueError()

    assert not dg.materialize_to_memory([asset1], raise_on_error=False).success


def test_selection():
    @dg.asset
    def upstream(): ...

    @dg.asset
    def downstream(upstream): ...

    assets = [upstream, downstream]

    result1 = dg.materialize_to_memory(assets, selection=[upstream])
    assert result1.success
    materialization_events = result1.get_asset_materialization_events()
    assert len(materialization_events) == 1
    assert materialization_events[0].materialization.asset_key == dg.AssetKey("upstream")
