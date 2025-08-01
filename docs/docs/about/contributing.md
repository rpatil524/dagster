---
description: Set up a local Dagster development environment and contribute code and documentation to the Dagster open source project.
sidebar_position: 20
title: Contributing
---

We love to see our community members get involved! If you are planning to contribute to Dagster, you will first need to set up a local development environment.

## Environment setup

You can develop for Dagster using macOS, Linux, or Windows. If using Windows, you will need to install and use [WSL](https://learn.microsoft.com/windows/wsl/install) to follow the steps in this guide.

1. Clone the Dagster repository to the destination of your choice:

   ```bash
   git clone git@github.com:dagster-io/dagster.git
   cd dagster
   ```

2. [Install uv](https://docs.astral.sh/uv/getting-started/installation). You can use `curl` to download the script and execute it with `sh`:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. Create and activate a virtual environment using uv with a Python version that Dagster supports:

   ```bash
   uv venv --python 3.12
   source .venv/bin/activate
   ```

   Dagster supports Python 3.9 through 3.12.

4. Ensure that you have a supported version of [node](https://nodejs.org/en/download) (20.X and above) by running `node -v`, and that you have [yarn](https://yarnpkg.com/lang/en) installed. Once you have node installed, you can use `npm` to install yarn.

   ```bash
   npm install --global yarn
   ```

5. Run `make dev_install` at the root of the repository. This sets up a full Dagster developer environment with all modules and runs tests that do not require heavy external dependencies such as docker.

   ```bash
   make dev_install
   ```

   This will take a few minutes.

<details>
  <summary>Note for Macs with an Apple silicon chip</summary>

    Some users have reported installation problems due to missing wheels for arm64 Macs when installing the `grpcio` package. To install the `dagster` development environment using our pre-built wheel of the `grpcio` package for M1, M2, and M3 machines, run `make dev_install_m1_grpcio_wheel` instead of `make dev_install`.

 </details>

6. Verify `dagster` and `dagster-webserver` are installed and editable

   ```bash
   $ dagster --version
   dagster, version 1!0+dev

   $ dagster-webserver --version
   dagster-webserver, version 1!0+dev
   ```

   As long as you see `version 1!0+dev` in the output, you are all set up and ready to start making code changes to Dagster! 🎉

7. (optional)

   You can further verify your environment is set up by running Dagster's test suite, however this can take an hour or more to complete.

   ```bash
   python -m pytest python_modules/dagster/dagster_tests
   ```

   To run only some of the tests, see [this page](https://docs.pytest.org/en/stable/how-to/usage.html#specifying-which-tests-to-run) of the `pytest` documentation.

## Developing Dagster

Some notes on developing in Dagster:

- **Ruff/Pyright**: We use [ruff](https://github.com/charliermarsh/ruff) for formatting, linting and import sorting, and [pyright](https://github.com/microsoft/pyright) for static type-checking. We test these in our CI/CD pipeline.
  - Run `make ruff` from the repo root to format, sort imports, and autofix some lint errors. It will also print out errors that need to be manually fixed.
  - Run `make pyright` from the repo root to analyze the whole repo for type-correctness. Note that the first time you run this, it will take several minutes because a new virtualenv will be constructed.
- **Line Width**: We use a line width of 100.
- **IDE**: We recommend setting up your IDE to format and check with ruff on save, but you can always run `make ruff` in the root Dagster directory before submitting a pull request. If you're also using VS Code, you can see what we're using for our `settings.json` [here](https://gist.github.com/natekupp/7a17a9df8d2064e5389cc84aa118a896).
- **Docker**: Some tests require [Docker Desktop](https://www.docker.com/products/docker-desktop) to be able to run them locally.

## Developing the Dagster webserver/UI

For development, run an instance of the webserver providing GraphQL service on a different port than the webapp, with any pipeline. For example:

```bash
cd examples/docs_snippets/docs_snippets/intro_tutorial/basics/connecting_ops/
dagster-webserver -p 3333 -f complex_job.py
```

Keep this running. Then, in another terminal, run the local development (autoreloading, etc.) version of the webapp:

:::tip
Don't forget to activate the virtual environment (`source .venv/bin/activate`) when you open another terminal!
:::

```bash
cd js_modules/dagster-ui
make dev_webapp
```

During development, you might find these commands useful. Run them from `js_modules/dagster-ui`:

- `yarn ts`: Typescript typechecking
- `yarn lint`: Linting with autofix
- `yarn jest`: An interactive Jest test runner that runs only affected tests by default

To run all of them together, run `yarn test`.

## Developing documentation

To run the Dagster documentation website locally, run the following commands:

```bash
cd docs
```

```bash
yarn install && yarn start
```

API documentation is built separately using Sphinx&mdash;if you change any `.rst` files, be sure to run the following command in the `docs` directory:

```bash
yarn build-api-docs
```

For the full guidelines for writing and debugging documentation, please refer to the [docs/README.md](https://github.com/dagster-io/dagster/blob/master/docs/README.md) and [docs/CONTRIBUTING.md](https://github.com/dagster-io/dagster/blob/master/docs/CONTRIBUTING.md) documents.

## Picking a GitHub Issue

We encourage you to start with an issue labeled with the tag [`good first issue`](https://github.com/dagster-io/dagster/issues?q=is%3Aopen+is%3Aissue+label%3A%22type%3A+good+first+issue%22) on the [Github issue board](https://github.com/dagster-io/dagster/issues), to get familiar with our codebase as a first-time contributor.

When you are ready for more of a challenge, you can tackle issues with the [most 👍 reactions](https://github.com/dagster-io/dagster/issues?q=is%3Aissue+is%3Aopen+sort%3Areactions-%2B1-desc). We factor engagement into prioritization of the issues. You can also explore other labels and pick any issue based on your interest.

## Submit Your Code

To submit your code, [fork the Dagster repository](https://help.github.com/en/articles/fork-a-repo), create a [new branch](https://help.github.com/en/desktop/contributing-to-projects/creating-a-branch-for-your-work) on your fork, and open [a Pull Request (PR)](https://help.github.com/en/articles/creating-a-pull-request-from-a-fork) once your work is ready for review.

In the PR template, please describe the change, including the motivation/context, test coverage, and any other relevant information. Please note if the PR is a breaking change or if it is related to an open GitHub issue.

A Core reviewer will review your PR in around one business day and provide feedback on any changes it requires to be approved. Once approved and all the tests (including Buildkite!) pass, the reviewer will click the Squash and merge button in GitHub 🥳.

Your PR is now merged into Dagster! We’ll shout out your contribution in the weekly release notes.
