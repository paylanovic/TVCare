# Security and privacy

TVCare controls a user-authorized Android TV through ADB. The HTTP interface binds only to loopback and requires a per-process bearer token. It is not intended to run on a public server or behind a public reverse proxy.

Do not post ADB keys, keystores, pairing codes, session URLs, raw TV logs, transaction journals, serial numbers or network addresses in issues. Use TVCare's sanitized report and review it yourself before sharing.

For a vulnerability, use GitHub's private vulnerability reporting when available (Security → Report a vulnerability). Do not publish exploit details or private data in a public issue. A public issue can request a private contact route without including sensitive details.

The companion APK only addresses a specific profiled TCL/Realtek shutdown fault. Other devices are not automatically eligible. A package/build test does not establish physical-device reliability.

No telemetry or automated report uploads are included. Runtime backups remain on the user's computer; the public source and release archives must not contain them.
