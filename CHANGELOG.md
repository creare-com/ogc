# Changelog
## 0.5.0

### Introduction
Support for Environmental Data Retrieval (EDR) was added in this version to extend OGC capabilities.
EDR is optional and can be enabled via the OGC_SUPPORTED_FORMATS environmental variable.
The currently supported version of EDR is v1.1.0. Additionally, the repository was modernized by
adding a development container, pyproject.toml, and Github Actions for linting, formatting, 
unit testing and scanning.

### Features
* Added support for EDR v1.1.0.

### Maintenance
* Added unit testing for code coverage requirements.
* Added development container and pyproject.toml file.
* Added Github Actions for linting, formatting, unit testing, and scanning.

### Bugfixes
* Fixed formatting, linting, and SonarQube errors to pass CI/CD scans.