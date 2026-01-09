import setuptools
from typing import List
import distutils.text_file
from pathlib import Path


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


def _parse_requirements(filename: str) -> List[str]:
    """Return requirements from requirements file."""
    # Ref: https://stackoverflow.com/a/42033122/
    return distutils.text_file.TextFile(
        filename=str(Path(__file__).with_name(filename))
    ).readlines()


setuptools.setup(
    name="clickup-api-client",
    author="Gavka Serhiy",
    author_email="sgavka@gmail.com",
    description="clickup-api-client: A Python client for the ClickUp API",
    keywords="clickup, clickup api, python, clickup-api-client, sdk",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sgavka/clickup-sdk",
    project_urls={
        "Bug Reports": "https://github.com/sgavka/clickup-sdk/issues",
        "Source Code": "https://github.com/sgavka/clickup-sdk",
    },
    packages=setuptools.find_packages(),
    python_requires=">=3.6",
    install_requires=[
        "pydantic",
        "typing-extensions",
        "word2number",
        "timefhuman",
        "pendulum",
        "typing-extensions",
        "setuptools",
    ],
    # extras_require='requirements.txt',
    # entry_points={
    #     'console_scripts': [  # This can provide executable scripts
    #         'run=examplepy:main',
    # You can execute `run` in bash to run `main()` in src/examplepy/__init__.py
    #     ],
    # },
)
