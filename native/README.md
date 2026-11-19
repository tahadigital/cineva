# Vrelio Apple Native Apps

The legacy single-file macOS launcher previously located here has been superseded by the unified Apple project in [`../apple/`](../apple/):

- **macOS (`app.vrelio.macos`)**: `apple/macOS/` + `apple/Shared/` — standalone `Vrelio.app` bundling `vrelio-server` (`PyInstaller --onedir`), native SwiftUI launch overlay & preferences, `WKWebView`, ad-hoc signing, `Vrelio-macOS.dmg`, and `Vrelio-macOS.zip`.
- **iOS / iPadOS (`app.vrelio.ios`)**: `apple/iOS/` + `apple/Shared/` — universal SwiftUI + `AVKit` (`AVPlayer`, PiP, AirPlay) app with Demo/M3U/Xtream/LAN sync and R4/R5 cloud flows.
- **XcodeGen & Tests**: `apple/project.yml` and `apple/Tests/VrelioIOSTests.swift`.
