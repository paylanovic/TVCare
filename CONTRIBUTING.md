# Contributing

Please open an issue describing the user-visible problem before a large change. Keep device-profile changes separate from general maintenance behavior.

## Local development

Python 3.10+ is required; the application has no third-party Python runtime dependency.

```sh
python -m tvbakim --demo
python -m unittest discover -s tests -v
python scripts/privacy_check.py --source
```

Real TV access is not part of unit tests or CI. Demo data must remain clearly labelled synthetic. Never add raw device logs, local transaction records, ADB authorization keys, signing keys, credentials, or personal build paths to a commit.

## New device support

Provide a sanitized device profile and a reproducible description. Do not assume every device from a manufacturer has the same package dependencies or power behavior. Changes must preserve read-before-write, explicit plans, identity checks, and exact rollback. Include meaningful tests for failure/recovery behavior. State firmware and physical test scope without publishing serial numbers.

## Signing and builds

Build keys live outside the repository and are supplied by environment variables. The committed companion APK is a signed release artifact, not a private key. A fork needs its own signing key; it cannot update an already-installed APK signed by another key.

Target packages must be built on each target operating system. See docs/DISTRIBUTION.md. All release assets need a privacy scan and package smoke test before publication.
