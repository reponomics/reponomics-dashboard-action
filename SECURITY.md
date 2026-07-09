# Security Policy

The Reponomics Dashboard project is in public development, but is not intended or recommended for general public use at this time. We invite anyone who is interested in joining the pre-release beta period to contact dashboard-beta@reponomics.org.

The project involves handling of GitHub traffic data (which is privileged to repo admins), retained workflow artifacts, generated dashboard HTML pages, and dashboard encryption keys - privacy and security are at the core of the product's design, and any vulnerability reports based on personal investigation or by security experts is strongly welcomed. That being said, the Reponomics organization does not store any user/owner-collected data whatsoever. 

## Supported Versions

No stable production version is supported yet. Until the first stable release, security fixes will generally land on `main` and then be included in the next pre-release or release tag.

## Reporting a Vulnerability

Please do not open a public issue for a suspected vulnerability.

Use GitHub [private vulnerability reporting](https://github.com/reponomics/reponomics-dashboard-action/security/advisories/new) for this repository. If you have volunteered to join the beta group, you will receive a response within 48 hours and we will determine the appropriate method and timeline for a resolution if a problem is identified. Other users are encouraged to report any findings, and swift action will be taken as deemed appropriate, but due to the pre-release status, we make no specific guarantees to the public at large. Again, we currently do not recommend the use of this project without prior contact - this is so that we can ensure that those who are using the product are guaranteed the highest level of support that we can provide.

## Scope

Reponomics Dashboard maintainers will respond to vulnerability reports pertaining to the project's infrastructure, the generated template repository, or the GitHub action. This includes:

- generated dashboard HTML and JavaScript;
- dashboard encryption and decryption behavior;
- retained dashboard data artifact encryption, restore, and upload behavior;
- workflow permissions, token handling, and release automation;
- vendored browser assets and their recorded upstream metadata;
- release notice parsing and rendering;
- action inputs and outputs that may expose sensitive data.

## The Security Practices of the Reponomics Dashboard Project

For information about the security protocols followed by the development repository and other supply chain related matters, see [REPO_SECURITY_PRACTICES](docs/REPO_SECURITY_PRACTICES.md).
