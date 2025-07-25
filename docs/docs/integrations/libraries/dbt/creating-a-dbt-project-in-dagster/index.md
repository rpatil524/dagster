---
title: 'Creating a dbt project in a Dagster project'
description: Dagster can orchestrate dbt alongside other technologies.
sidebar_position: 200
---

:::note

Using dbt Cloud? Check out the [Dagster & dbt Cloud documentation](/integrations/libraries/dbt/dbt-cloud).

:::

In this tutorial, we'll walk you through integrating dbt with Dagster using a smaller version of dbt's example [jaffle shop project](https://github.com/dbt-labs/jaffle_shop), the [dagster-dbt library](/api/libraries/dagster-dbt), and a data warehouse, such as [DuckDB](https://duckdb.org).

By the end of this tutorial, you'll have your dbt models represented in Dagster along with other [Dagster asset definitions](/integrations/libraries/dbt/reference#dbt-models-and-dagster-asset-definitions) upstream and downstream of them:

![Asset group with dbt models and Python asset](/images/integrations/dbt/creating-a-dbt-project-in-dagster/downstream-assets/asset-graph-materialized.png)

To get there, you will:

- [Set up a dbt project](/integrations/libraries/dbt/creating-a-dbt-project-in-dagster/set-up-dbt-project)
- [Load the dbt models into Dagster as assets](/integrations/libraries/dbt/creating-a-dbt-project-in-dagster/load-dbt-models)
- [Create and materialize upstream Dagster assets](/integrations/libraries/dbt/creating-a-dbt-project-in-dagster/upstream-assets)
- [Create and materialize a downstream asset](/integrations/libraries/dbt/creating-a-dbt-project-in-dagster/downstream-assets) that outputs a plotly chart

## Prerequisites

To complete this tutorial, you'll need:

- **To have [git](https://en.wikipedia.org/wiki/Git) installed**. If it's not installed already (find out by typing `git` in your terminal), you can install it using the [instructions on the git website](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).

- **To install dbt, Dagster, and the Dagster webserver/UI**. Run the following to install everything using pip:

  <PackageInstallInstructions packageName="dagster-dbt dbt-duckdb" />

  The `dagster-dbt` library installs both `dbt-core` and `dagster` as dependencies. `dbt-duckdb` is installed as you'll be using [DuckDB](https://duckdb.org) as a database during this tutorial. Refer to the [dbt](https://docs.getdbt.com/dbt-cli/install/overview) and [Dagster](/getting-started/installation) installation docs for more info.

## Ready to get started?

When you've fulfilled all the prerequisites for the tutorial, you can get started by [setting up the dbt project](/integrations/libraries/dbt/creating-a-dbt-project-in-dagster/set-up-dbt-project).
