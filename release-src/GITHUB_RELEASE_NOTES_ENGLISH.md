## Plants vs. Zombies Hybrid v0.25 — English for macOS

This release provides an unofficial, standalone English edition of Plants vs.
Zombies Hybrid v0.25 for macOS. Windows, CrossOver, and a separate .NET
installation are not required.

### English localization

- Contextual English text for menus, levels, dialogue, the Almanac, the shop,
  Custom Levels, settings, and the command interface
- Redrawn English interface graphics based on the original artwork
- Original hover, pressed, selected, disabled, and locked interaction states
  retained
- Layout adjustments for longer English labels without changing button hit
  areas, navigation, audio, or gameplay behavior

### Compatibility fixes

- Correct parsing of numeric command arguments, including `/coin 100000`
- Restored in-game graphical command panel
- Correct handling of `/debug openalllevel on`
- `/win` enters the normal level-completion flow
- Friendly, charmed, and player-controlled zombies no longer block wave
  progression or level completion

### Requirements

- macOS 13 or later
- Intel Mac, or an Apple silicon Mac with Rosetta 2
- About 1.5 GB of free disk space

The installer checks for Rosetta 2 on Apple silicon. If it is missing, the
installer uses Apple Software Update to install the official component.

### Installation

1. Download and open `PVZ-Hybrid-v0.25-English-macOS-Installer.dmg`.
2. Double-click `Install Plants vs. Zombies Hybrid v0.25 English.pkg`.
3. Complete the steps in the macOS Installer.
4. Open the game from Launchpad or the Applications folder.

The English app and its saved games are separate from the Chinese release.

### macOS security notice

This community build is ad-hoc signed and is not notarized because it is not
distributed with an Apple Developer ID certificate. If macOS blocks the
installer, Control-click the package in Finder, choose **Open**, and confirm.
Managed Macs may prohibit unnotarized software.

### File verification

```sh
shasum -a 256 -c PVZ-Hybrid-v0.25-English-macOS-Installer.dmg.sha256
```

This is an unofficial compatibility release and is not affiliated with,
sponsored by, or authorized by the game's creators, publishers, or other rights
holders. Game content, names, characters, trademarks, and related assets remain
the property of their respective rights holders.
