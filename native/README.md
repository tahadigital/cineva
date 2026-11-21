# Mavie Apple Native Apps

The legacy single-file macOS launcher previously located here has been superseded by the unified Apple project in [`../apple/`](../apple/):

- **macOS (`app.mavie.macos`)**: `apple/macOS/` + `apple/Shared/` — standalone `Mavie.app` bundling `mavie-server` (`PyInstaller --onedir`), native SwiftUI launch overlay & preferences, `WKWebView`, ad-hoc signing, `Mavie-macOS.dmg`, and `Mavie-macOS.zip`.
- **iOS / iPadOS (`app.mavie.ios`)**: `apple/iOS/` + `apple/Shared/` — universal SwiftUI + `AVKit` (`AVPlayer`, PiP, AirPlay) app with Demo/M3U/Xtream/LAN sync and R4/R5 cloud flows.
- **XcodeGen & Tests**: `apple/project.yml` and `apple/Tests/MavieIOSTests.swift`.
