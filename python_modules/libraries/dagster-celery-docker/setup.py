from pathlib import Path

from setuptools import find_packages, setup


def get_version() -> str:
    version: dict[str, str] = {}
    with open(Path(__file__).parent / "dagster_celery_docker/version.py", encoding="utf8") as fp:
        exec(fp.read(), version)

    return version["__version__"]


ver = get_version()
# dont pin dev installs to avoid pip dep resolver issues
pin = "" if ver == "1!0+dev" else f"=={ver}"
setup(
    name="dagster-celery-docker",
    version=ver,
    author="Dagster Labs",
    license="Apache-2.0",
    description="A Dagster integration for celery-docker",
    url="https://github.com/dagster-io/dagster/tree/master/python_modules/libraries/dagster-celery-docker",
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(exclude=["dagster_celery_docker_tests*"]),
    include_package_data=True,
    python_requires=">=3.9,<3.14",
    install_requires=[
        f"dagster{pin}",
        f"dagster-celery{pin}",
        f"dagster-graphql{pin}",
        "docker",
    ],
    extras_require={
        "test": [
            "botocore>=1.21.49",  # first botocore version that works on python 3.9+
        ],
    },
    zip_safe=False,
)
