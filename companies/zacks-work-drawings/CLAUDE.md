# Zack's Work Drawings — Project Brain

## Overview
Flutter Android app for browsing machine wiring diagrams and SOPs from a Google Drive folder called `machine docs`. Pure-black theme, 2-column colored folder grid, full-filename search across every folder, built-in PDF viewer with pinch-zoom, and offline caching (any PDF opened once is viewable without internet).

## Status
- **Mode:** personal use only, not a product
- **Target:** Android 8.0+ (minSdk 26)
- **Package ID:** `com.zedwards1226.zacks_work_drawings`
- **Short name on launcher:** ZWD

## Prereqs (one-time)
1. Flutter SDK at `C:\flutter` (already installed — stable 3.41.x)
2. Android SDK at `C:\android` (already installed; env `ANDROID_HOME` already set)
3. Java 17 Temurin (already installed)
4. Google OAuth client ID (Android type) registered in Google Cloud Console against SHA-1 fingerprint of whichever keystore signs the APK. See `README.md` for walkthrough. Zach creates this himself (credentials hard-stop).
5. Google Drive must contain a folder literally named `machine docs` with the 11 named subfolders (see `lib/models/folder_config.dart`).

## Build Commands
```bash
cd C:\ZachAI\companies\zacks-work-drawings
flutter pub get
flutter analyze           # must be clean
flutter test              # model/folder tests
flutter build apk --debug # APK at build/app/outputs/flutter-apk/app-debug.apk
```

## Folder Structure
```
companies/zacks-work-drawings/
├── CLAUDE.md
├── ACTIVE_FILES.md
├── README.md
├── pubspec.yaml
├── analysis_options.yaml
├── .gitignore
├── android/           # flutter create scaffolding (gradle kts)
├── assets/icon/       # lightning_bolt.png source for app icon
├── lib/
│   ├── main.dart
│   ├── models/        # folder_config.dart, drive_file.dart
│   ├── services/      # auth_service, drive_service, cache_service
│   ├── providers/     # library_provider (ChangeNotifier)
│   ├── screens/       # sign_in, home, folder, search_results, pdf_viewer
│   └── widgets/       # folder_tile, file_list_tile, search_bar_widget
├── test/widget_test.dart
└── tools/gen_icon.py  # regenerates lightning_bolt.png via PIL
```

## Protections / Auto-Merge
- No live-trading or money-moving code — standard auto-merge policy applies.
- No credentials or OAuth client secrets committed — only public OAuth client ID goes in source (Android uses SHA-1 instead of secret).

## Known Gotchas
- Drive folder names are **case-sensitive**. `line 5` won't match `Line 5`.
- First launch calls `google_sign_in` which requires SHA-1 of the APK signing key to match the one registered in Google Cloud.
- Debug APK uses `~/.android/debug.keystore` — register its SHA-1 in Cloud Console. Release APK needs its own keystore (not yet configured).
