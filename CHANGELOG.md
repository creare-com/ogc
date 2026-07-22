# Changelog
## 0.6.1
### Introduction
Covered additional security-relevant cases.

### Maintenance
* Added input validation
* Added exception sanitization
* Added checks for invalid relative paths and symlinks

## 0.6.0

### Introduction
Support for Web Map Tile Service (WMTS) was added in this version to extend OGC capabilities.
WMTS is optional and can be enabled via the OGC_SUPPORTED_FORMATS environmental variable.
The currently supported version of WMTS is v1.0.0. Additionally, optional hierarchical layering 
was added within WMS GetCapabilities. Code quality and security was improved by reducing blind 
exceptions and sanitizing error messages.

### Features
* Added support for WMTS v1.0.0.
* Added support for hierarchical layering in WMS Get GetCapabilities.

### Maintenance
* Added unit testing for code coverage requirements.
* Reduced blind exceptions and replaced with specific exception catching.
* Sanitized error messaging to avoid exposing data to end-users.  

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