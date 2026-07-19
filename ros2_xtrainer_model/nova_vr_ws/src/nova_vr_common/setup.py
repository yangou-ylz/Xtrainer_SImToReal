from setuptools import find_packages, setup

package_name = "nova_vr_common"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", ["launch/logging_smoke_test.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Nova VR Project",
    maintainer_email="user@example.com",
    description="Shared utilities for Nova VR teleoperation packages.",
    license="BSD-3-Clause",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "logging_smoke_test = nova_vr_common.logging_smoke_test:main",
        ],
    },
)
