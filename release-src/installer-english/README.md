# English macOS installer

This directory builds the standalone English installer:

```text
PVZ-Hybrid-v0.25-English-macOS-Installer.dmg
└── Install Plants vs. Zombies Hybrid v0.25 English.pkg
    └── /Applications/Plants vs. Zombies Hybrid v0.25 English.app
```

The installed game does not require Windows or CrossOver. On Apple silicon, the
pre-install script verifies Rosetta 2 and installs it through Apple Software
Update when necessary.

Build from an assembled app:

```sh
release-src/installer-english/build-installer.sh \
  --app "/path/to/Plants vs. Zombies Hybrid v0.25 English.app"
```

Without Apple Developer certificates, the script creates an ad-hoc-signed app,
an unsigned product package, and an unnotarized disk image. For public notarized
distribution, supply Developer ID Application and Developer ID Installer
identities plus a `notarytool` keychain profile.
