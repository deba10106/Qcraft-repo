# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from setuptools import setup, find_packages
import os

try:
    with open("README_PYPI.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()
except FileNotFoundError:
    try:
        with open("README.md", "r", encoding="utf-8") as fh:
            long_description = fh.read()
    except FileNotFoundError:
        long_description = "Qcraft: Quantum Circuit Design, Optimization, and Surface Code Mapping Platform"

setup(
    name='qcraft',
    version='0.1.6',
    description='Qcraft: Quantum Circuit Design, Optimization, and Surface Code Mapping Platform',
    long_description=long_description,
    long_description_content_type="text/markdown",

    author='Debasis Mondal',
    packages=find_packages(),
    install_requires=[
        'PySide6==6.9.3',
        'PyYAML==6.0.3',
        'jsonschema==4.25.1',
        'networkx==3.5',
        'matplotlib==3.10.6',
        'numpy==2.3.3',
        'stable-baselines3==2.7.0',
        'scikit-learn==1.7.2',
        'pandas==2.3.3',
        'gymnasium==1.2.1',
        'stim==1.15.0',
        'pymatching==2.3.1',
        'python-dotenv==1.1.1',
    ],
    extras_require={
        'qiskit': [
            'qiskit==2.2.1',
            'qiskit-aer==0.17.2',
            'qiskit-ibm-runtime==0.42.0',
        ],
        'security': [
            'cryptography==46.0.2',
            'keyring==25.6.0',
        ],
        # Install Torch separately to match your CUDA runtime.
        # CPU-only example: pip install 'qcraft[torch-cpu]'
        # CUDA 12.1 example: pip install 'qcraft[torch-cu121]' --extra-index-url https://download.pytorch.org/whl/cu121
        'torch-cpu': [
            'torch==2.4.0',
        ],
        'torch-cu121': [
            'torch==2.4.0',
        ],
        # Optional cloud extras
        'cloud-gcp': [
            'google-cloud-aiplatform==1.119.0',
            'google-cloud-storage==2.19.0',
            'google-cloud-logging==3.12.1',
        ],
        'cloud-aws': [
            'boto3==1.40.46',
        ],
        'dev': [
            'pytest==7.4.2',
            'psutil==7.1.0',
        ],
        'full': [
            'qiskit==2.2.1',
            'qiskit-aer==0.17.2',
            'qiskit-ibm-runtime==0.42.0',
            'cryptography==46.0.2',
            'keyring==25.6.0',
        ]
    },
    entry_points={
        'console_scripts': [
            'qcraft = circuit_designer.gui_main:main',
        ],
    },
    include_package_data=True,
) 
