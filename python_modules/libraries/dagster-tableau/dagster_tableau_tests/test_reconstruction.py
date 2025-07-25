from unittest.mock import MagicMock

import pytest
from dagster import AssetExecutionContext
from dagster._core.code_pointer import CodePointer
from dagster._core.definitions.assets.definition.asset_spec import AssetSpec
from dagster._core.definitions.definitions_class import Definitions
from dagster._core.definitions.reconstruct import (
    ReconstructableJob,
    ReconstructableRepository,
    initialize_repository_def_from_pointer,
    reconstruct_repository_def_from_pointer,
)
from dagster._core.definitions.unresolved_asset_job_definition import define_asset_job
from dagster._core.events import DagsterEventType
from dagster._core.execution.api import create_execution_plan, execute_plan
from dagster._core.instance_for_test import instance_for_test
from dagster._utils.test.definitions import definitions
from dagster_tableau.asset_decorator import tableau_assets
from dagster_tableau.asset_utils import parse_tableau_external_and_materializable_asset_specs
from dagster_tableau.assets import build_tableau_materializable_assets_definition
from dagster_tableau.resources import TableauCloudWorkspace, load_tableau_asset_specs
from dagster_tableau.translator import DagsterTableauTranslator, TableauTranslatorData

from dagster_tableau_tests.conftest import (
    FAKE_CONNECTED_APP_CLIENT_ID,
    FAKE_CONNECTED_APP_SECRET_ID,
    FAKE_CONNECTED_APP_SECRET_VALUE,
    FAKE_POD_NAME,
    FAKE_SITE_NAME,
    FAKE_USERNAME,
)


@definitions
def cacheable_asset_defs():
    resource = TableauCloudWorkspace(
        connected_app_client_id=FAKE_CONNECTED_APP_CLIENT_ID,
        connected_app_secret_id=FAKE_CONNECTED_APP_SECRET_ID,
        connected_app_secret_value=FAKE_CONNECTED_APP_SECRET_VALUE,
        username=FAKE_USERNAME,
        site_name=FAKE_SITE_NAME,
        pod_name=FAKE_POD_NAME,
    )

    tableau_specs = load_tableau_asset_specs(
        workspace=resource,
    )

    external_asset_specs, materializable_asset_specs = (
        parse_tableau_external_and_materializable_asset_specs(tableau_specs)
    )

    resource_key = "tableau"

    return Definitions(
        assets=[
            # We don't pass a list of refreshable IDs - we yield observe results without refreshing Tableau assets.
            build_tableau_materializable_assets_definition(
                resource_key=resource_key,
                specs=materializable_asset_specs,
            ),
            *external_asset_specs,
        ],
        jobs=[define_asset_job("all_asset_job")],
        resources={resource_key: resource},
    )


@definitions
def cacheable_asset_defs_refreshable_workbooks():
    resource = TableauCloudWorkspace(
        connected_app_client_id=FAKE_CONNECTED_APP_CLIENT_ID,
        connected_app_secret_id=FAKE_CONNECTED_APP_SECRET_ID,
        connected_app_secret_value=FAKE_CONNECTED_APP_SECRET_VALUE,
        username=FAKE_USERNAME,
        site_name=FAKE_SITE_NAME,
        pod_name=FAKE_POD_NAME,
    )
    tableau_specs = load_tableau_asset_specs(
        workspace=resource,
    )

    external_asset_specs, materializable_asset_specs = (
        parse_tableau_external_and_materializable_asset_specs(tableau_specs)
    )

    resource_key = "tableau"

    return Definitions(
        assets=[
            build_tableau_materializable_assets_definition(
                resource_key=resource_key,
                specs=materializable_asset_specs,
                refreshable_workbook_ids=["b75fc023-a7ca-4115-857b-4342028640d0"],
            ),
            *external_asset_specs,
        ],
        jobs=[define_asset_job("all_asset_job")],
        resources={resource_key: resource},
    )


@definitions
def cacheable_asset_defs_refreshable_data_sources():
    resource = TableauCloudWorkspace(
        connected_app_client_id=FAKE_CONNECTED_APP_CLIENT_ID,
        connected_app_secret_id=FAKE_CONNECTED_APP_SECRET_ID,
        connected_app_secret_value=FAKE_CONNECTED_APP_SECRET_VALUE,
        username=FAKE_USERNAME,
        site_name=FAKE_SITE_NAME,
        pod_name=FAKE_POD_NAME,
    )

    tableau_specs = load_tableau_asset_specs(
        workspace=resource,
    )

    external_asset_specs, materializable_asset_specs = (
        parse_tableau_external_and_materializable_asset_specs(
            tableau_specs, include_data_sources_with_extracts=True
        )
    )

    resource_key = "tableau"

    return Definitions(
        assets=[
            build_tableau_materializable_assets_definition(
                resource_key=resource_key,
                specs=materializable_asset_specs,
                refreshable_data_source_ids=["1f5660c7-3b05-5ff0-90ce-4199226956c6"],
            ),
            *external_asset_specs,
        ],
        jobs=[define_asset_job("all_asset_job")],
        resources={resource_key: resource},
    )


@definitions
def cacheable_asset_defs_asset_decorator_with_context():
    resource = TableauCloudWorkspace(
        connected_app_client_id=FAKE_CONNECTED_APP_CLIENT_ID,
        connected_app_secret_id=FAKE_CONNECTED_APP_SECRET_ID,
        connected_app_secret_value=FAKE_CONNECTED_APP_SECRET_VALUE,
        username=FAKE_USERNAME,
        site_name=FAKE_SITE_NAME,
        pod_name=FAKE_POD_NAME,
    )

    @tableau_assets(workspace=resource)
    def my_tableau_assets(context: AssetExecutionContext, tableau: TableauCloudWorkspace):
        yield from tableau.refresh_and_poll(context=context)

    return Definitions(
        assets=[my_tableau_assets],
        jobs=[
            define_asset_job("all_asset_job"),
            define_asset_job("subset_asset_job", selection="hidden_sheet_datasource"),
        ],
        resources={"tableau": resource},
    )


@definitions
def cacheable_asset_defs_custom_translator():
    resource = TableauCloudWorkspace(
        connected_app_client_id=FAKE_CONNECTED_APP_CLIENT_ID,
        connected_app_secret_id=FAKE_CONNECTED_APP_SECRET_ID,
        connected_app_secret_value=FAKE_CONNECTED_APP_SECRET_VALUE,
        username=FAKE_USERNAME,
        site_name=FAKE_SITE_NAME,
        pod_name=FAKE_POD_NAME,
    )

    class MyCoolTranslator(DagsterTableauTranslator):
        def get_asset_spec(self, data: TableauTranslatorData) -> AssetSpec:
            default_spec = super().get_asset_spec(data)
            return default_spec.replace_attributes(key=default_spec.key.with_prefix("my_prefix"))

    tableau_specs = load_tableau_asset_specs(
        workspace=resource, dagster_tableau_translator=MyCoolTranslator()
    )

    return Definitions(assets=[*tableau_specs], jobs=[define_asset_job("all_asset_job")])


def test_load_assets_workspace_data_refreshable_workbooks(
    sign_in: MagicMock,
    get_workbooks: MagicMock,
    get_workbook: MagicMock,
    get_view: MagicMock,
    get_job: MagicMock,
    refresh_workbook: MagicMock,
    cancel_job: MagicMock,
) -> None:
    with instance_for_test() as instance:
        assert sign_in.call_count == 0
        assert get_workbooks.call_count == 0
        assert get_workbook.call_count == 0
        assert get_view.call_count == 0
        assert refresh_workbook.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # first, we resolve the repository to generate our cached metadata
        pointer = CodePointer.from_python_file(
            __file__,
            "cacheable_asset_defs_refreshable_workbooks",
            None,
        )
        init_repository_def = initialize_repository_def_from_pointer(
            pointer,
        )

        # 3 calls to creates the defs
        assert sign_in.call_count == 1
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 0
        assert refresh_workbook.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # 3 Tableau external assets and 3 Tableau materializable assets
        assert len(init_repository_def.assets_defs_by_key) == 3 + 3

        repository_load_data = init_repository_def.repository_load_data

        # We use a separate file here just to ensure we get a fresh load
        recon_repository_def = reconstruct_repository_def_from_pointer(
            pointer,
            repository_load_data,
        )
        assert len(recon_repository_def.assets_defs_by_key) == 3 + 3

        # no additional calls after a fresh load
        assert sign_in.call_count == 1
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 0
        assert refresh_workbook.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # testing the job that materializes the tableau assets
        job_def = recon_repository_def.get_job("all_asset_job")
        recon_job = ReconstructableJob(
            repository=ReconstructableRepository(pointer),
            job_name="all_asset_job",
        )

        execution_plan = create_execution_plan(recon_job, repository_load_data=repository_load_data)
        run = instance.create_run_for_job(job_def=job_def, execution_plan=execution_plan)

        events = execute_plan(
            execution_plan=execution_plan,
            job=recon_job,
            dagster_run=run,
            instance=instance,
        )

        # the materialization of the multi-asset for the 3 materializable assets should be successful
        assert (
            len([event for event in events if event.event_type == DagsterEventType.STEP_SUCCESS])
            == 1
        ), "Expected one successful step"

        asset_materializations = [
            event for event in events if event.event_type == DagsterEventType.ASSET_MATERIALIZATION
        ]
        assert len(asset_materializations) == 3

        # 3 calls to create the defs + 7 calls to materialize the Tableau assets
        # with 1 workbook to refresh, 2 sheets and 1 dashboard
        assert sign_in.call_count == 2
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 3
        assert refresh_workbook.call_count == 1
        assert get_job.call_count == 2
        # The finish_code of the mocked get_job is 0, so no cancel_job is not called
        assert cancel_job.call_count == 0


def test_load_assets_workspace_data_refreshable_data_sources(
    sign_in: MagicMock,
    get_workbooks: MagicMock,
    get_workbook: MagicMock,
    get_view: MagicMock,
    get_data_source: MagicMock,
    get_job: MagicMock,
    refresh_data_source: MagicMock,
    cancel_job: MagicMock,
) -> None:
    with instance_for_test() as instance:
        assert sign_in.call_count == 0
        assert get_workbooks.call_count == 0
        assert get_workbook.call_count == 0
        assert get_view.call_count == 0
        assert get_data_source.call_count == 0
        assert refresh_data_source.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # first, we resolve the repository to generate our cached metadata
        pointer = CodePointer.from_python_file(
            __file__,
            "cacheable_asset_defs_refreshable_data_sources",
            None,
        )
        init_repository_def = initialize_repository_def_from_pointer(
            pointer,
        )

        # 3 calls to creates the defs
        assert sign_in.call_count == 1
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 0
        assert get_data_source.call_count == 0
        assert refresh_data_source.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # 4 Tableau external assets and 2 Tableau materializable assets
        assert len(init_repository_def.assets_defs_by_key) == 4 + 2

        repository_load_data = init_repository_def.repository_load_data

        # We use a separate file here just to ensure we get a fresh load
        recon_repository_def = reconstruct_repository_def_from_pointer(
            pointer,
            repository_load_data,
        )
        assert len(recon_repository_def.assets_defs_by_key) == 4 + 2

        # no additional calls after a fresh load
        assert sign_in.call_count == 1
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 0
        assert get_data_source.call_count == 0
        assert refresh_data_source.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # testing the job that materializes the tableau assets
        job_def = recon_repository_def.get_job("all_asset_job")
        recon_job = ReconstructableJob(
            repository=ReconstructableRepository(pointer),
            job_name="all_asset_job",
        )

        execution_plan = create_execution_plan(recon_job, repository_load_data=repository_load_data)
        run = instance.create_run_for_job(job_def=job_def, execution_plan=execution_plan)

        events = execute_plan(
            execution_plan=execution_plan,
            job=recon_job,
            dagster_run=run,
            instance=instance,
        )

        # the materialization of the multi-asset for the 4 materializable assets should be successful
        assert (
            len([event for event in events if event.event_type == DagsterEventType.STEP_SUCCESS])
            == 1
        ), "Expected one successful step"

        asset_materializations = [
            event for event in events if event.event_type == DagsterEventType.ASSET_MATERIALIZATION
        ]
        assert len(asset_materializations) == 4

        # 3 calls to create the defs + 8 calls to materialize the Tableau assets
        # with 1 data source to refresh, 2 sheets and 1 dashboard
        assert sign_in.call_count == 2
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 3
        assert get_data_source.call_count == 1
        assert refresh_data_source.call_count == 1
        assert get_job.call_count == 2
        # The finish_code of the mocked get_job is 0, so no cancel_job is not called
        assert cancel_job.call_count == 0


def test_load_assets_workspace_data(
    sign_in: MagicMock,
    get_workbooks: MagicMock,
    get_workbook: MagicMock,
    get_view: MagicMock,
    get_data_source: MagicMock,
    get_job: MagicMock,
    refresh_data_source: MagicMock,
    cancel_job: MagicMock,
) -> None:
    with instance_for_test() as instance:
        assert sign_in.call_count == 0
        assert get_workbooks.call_count == 0
        assert get_workbook.call_count == 0
        assert get_view.call_count == 0
        assert get_data_source.call_count == 0
        assert refresh_data_source.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # first, we resolve the repository to generate our cached metadata
        pointer = CodePointer.from_python_file(
            __file__,
            "cacheable_asset_defs",
            None,
        )
        init_repository_def = initialize_repository_def_from_pointer(
            pointer,
        )

        # 3 calls to creates the defs
        assert sign_in.call_count == 1
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 0
        assert get_data_source.call_count == 0
        assert refresh_data_source.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # 3 Tableau external assets and 3 Tableau materializable assets
        assert len(init_repository_def.assets_defs_by_key) == 3 + 3

        repository_load_data = init_repository_def.repository_load_data

        # We use a separate file here just to ensure we get a fresh load
        recon_repository_def = reconstruct_repository_def_from_pointer(
            pointer,
            repository_load_data,
        )
        assert len(recon_repository_def.assets_defs_by_key) == 3 + 3

        # no additional calls after a fresh load
        assert sign_in.call_count == 1
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 0
        assert get_data_source.call_count == 0
        assert refresh_data_source.call_count == 0
        assert get_job.call_count == 0
        assert cancel_job.call_count == 0

        # testing the job that materializes the tableau assets
        job_def = recon_repository_def.get_job("all_asset_job")
        recon_job = ReconstructableJob(
            repository=ReconstructableRepository(pointer),
            job_name="all_asset_job",
        )

        execution_plan = create_execution_plan(recon_job, repository_load_data=repository_load_data)
        run = instance.create_run_for_job(job_def=job_def, execution_plan=execution_plan)

        events = execute_plan(
            execution_plan=execution_plan,
            job=recon_job,
            dagster_run=run,
            instance=instance,
        )

        # the materialization of the multi-asset for the 3 materializable assets should be successful
        assert (
            len([event for event in events if event.event_type == DagsterEventType.STEP_SUCCESS])
            == 1
        ), "Expected one successful step"

        asset_materializations = [
            event for event in events if event.event_type == DagsterEventType.ASSET_MATERIALIZATION
        ]
        assert len(asset_materializations) == 3

        # 3 calls to create the defs + 3 calls to materialize the Tableau assets
        # with 1 workbook, 2 sheets and 1 dashboard
        assert sign_in.call_count == 2
        assert get_workbooks.call_count == 1
        assert get_workbook.call_count == 1
        assert get_view.call_count == 3
        # Nothing is refreshed via Dagster so these methods are not used
        assert get_data_source.call_count == 0
        assert refresh_data_source.call_count == 0
        assert get_job.call_count == 0
        # The finish_code of the mocked get_job is 0, so no cancel_job is not called
        assert cancel_job.call_count == 0


def test_load_assets_workspace_data_translator(
    sign_in: MagicMock,
    get_workbooks: MagicMock,
    get_workbook: MagicMock,
    get_view: MagicMock,
    get_job: MagicMock,
    refresh_workbook: MagicMock,
    cancel_job: MagicMock,
) -> None:
    with instance_for_test() as _instance:
        repository_def = initialize_repository_def_from_pointer(
            pointer=CodePointer.from_python_file(
                __file__,
                "cacheable_asset_defs_custom_translator",
                None,
            )
        )

        assert len(repository_def.assets_defs_by_key) == 6
        assert all(
            key.path[0] == "my_prefix" for key in repository_def.assets_defs_by_key.keys()
        ), repository_def.assets_defs_by_key


@pytest.mark.parametrize(
    "job_name, expected_asset_materializations, expected_asset_observations",
    [
        ("all_asset_job", 1, 3),
        ("subset_asset_job", 1, 0),
    ],
    ids=[
        "all_asset_job",
        "subset_asset_job",
    ],
)
def test_load_assets_workspace_asset_decorator_with_context(
    job_name: str,
    expected_asset_materializations: int,
    expected_asset_observations: int,
    sign_in: MagicMock,
    get_workbooks: MagicMock,
    get_workbook: MagicMock,
    get_view: MagicMock,
    get_data_source: MagicMock,
    get_job: MagicMock,
    refresh_data_source: MagicMock,
    cancel_job: MagicMock,
) -> None:
    with instance_for_test() as instance:
        pointer = CodePointer.from_python_file(
            __file__,
            "cacheable_asset_defs_asset_decorator_with_context",
            None,
        )
        repository_def = initialize_repository_def_from_pointer(
            pointer,
        )

        # 4 Tableau materializable assets
        assert len(repository_def.assets_defs_by_key) == 4

        repository_load_data = repository_def.repository_load_data

        # testing the job that materializes the tableau assets
        job_def = repository_def.get_job(job_name)
        recon_job = ReconstructableJob(
            repository=ReconstructableRepository(pointer),
            job_name=job_name,
        )

        execution_plan = create_execution_plan(recon_job, repository_load_data=repository_load_data)
        run = instance.create_run_for_job(job_def=job_def, execution_plan=execution_plan)

        events = execute_plan(
            execution_plan=execution_plan,
            job=recon_job,
            dagster_run=run,
            instance=instance,
        )

        # the materialization of the multi-asset for the 4 materializable assets should be successful
        assert (
            len([event for event in events if event.event_type == DagsterEventType.STEP_SUCCESS])
            == 1
        ), "Expected one successful step"

        asset_materializations = [
            event for event in events if event.event_type == DagsterEventType.ASSET_MATERIALIZATION
        ]
        assert len(asset_materializations) == expected_asset_materializations

        asset_observations = [
            event for event in events if event.event_type == DagsterEventType.ASSET_OBSERVATION
        ]
        assert len(asset_observations) == expected_asset_observations
