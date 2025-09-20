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
        'PySide6',
        'PyYAML',
        'jsonschema',
        'networkx',
        'matplotlib',
        'numpy',
        'stable-baselines3',
        'scikit-learn',
        'pandas',
        'torch',
        'gymnasium',
        'stim',
        'pymatching',
        'python-dotenv'
    ],
    extras_require={
        'qiskit': [
            'qiskit>=1.0',
            'qiskit-aer',
            'qiskit-ibm-runtime',
        ],
        'full': [
            'qiskit>=1.0',
            'qiskit-aer',
            'qiskit-ibm-runtime',
        ]
    },
    entry_points={
        'console_scripts': [
            'qcraft = circuit_designer.gui_main:main',
        ],
    },
    include_package_data=True,
    package_data={
        'scode': ['code_switcher/*.py'],
        'configs': ['*.json', '*.yaml'],
        'schemas': ['*.yaml'],
        'assets': ['*.svg'],
    },
) 
