# Zack's Work Drawings

Android app for browsing machine wiring diagrams and SOPs from Google Drive. Pure-black UI, 11 colored folder tiles, cross-folder filename search, built-in PDF viewer with pinch zoom, offline caching.

- **Package:** `com.zedwards1226.zacks_work_drawings`
- **Min Android:** 8.0 (API 26)
- **Short name:** ZWD
- **Tech:** Flutter 3.41 + syncfusion_flutter_pdfviewer + Google Drive API v3

## Quick build

```bash
cd C:\ZachAI\companies\zacks-work-drawings
flutter pub get
flutter analyze
flutter build apk --debug
# APK -> build/app/outputs/flutter-apk/app-debug.apk
```

Install on phone:
```bash
adb install build/app/outputs/flutter-apk/app-debug.apk
```

Or sideload: transfer APK to phone -> open -> allow install from this source.

## First-time setup (one-time only)

The APK won't sign in to Google Drive until an OAuth client ID is registered against the keystore that signed it.

### 1. Get your SHA-1 fingerprint

Debug builds (what `flutter build apk --debug` produces):
```powershell
keytool -list -v -keystore "$env:USERPROFILE\.android\debug.keystore" -alias androiddebugkey -storepass android -keypass android
```

Copy the `SHA1:` line.

### 2. Create an OAuth client in Google Cloud Console

1. Go to https://console.cloud.google.com/
2. Create a project (e.g., "Zack's Work Drawings")
3. APIs & Services -> Library -> enable **Google Drive API**
4. APIs & Services -> OAuth consent screen -> External, add your Gmail as test user
5. APIs & Services -> Credentials -> **Create Credentials -> OAuth client ID**
    - Application type: **Android**
    - Package name: `com.zedwards1226.zacks_work_drawings`
    - SHA-1: paste from step 1
6. Save. No client secret needed - Android uses SHA-1 + package name.

### 3. Put your machine docs in Google Drive

Create a folder at the top of your Drive named **exactly** `machine docs`. Inside it, create these 11 subfolders (case matters):

```
Line 5          Line 8           Line 9
Line 10         Line 11
Bema            Bundlers         Facial 2
Palletizer Robots
General Drives & Motors
General SOPs
```

Drop your PDFs into the appropriate subfolder. The app picks up changes on pull-to-refresh.

## Release APK (signed for distribution)

The debug APK works for personal sideloading. For a shareable release APK:

1. Generate a release keystore (keep the file safe, back it up):
    ```bash
    keytool -genkey -v -keystore %USERPROFILE%\.zwd-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias zwd
    ```
2. Get the release SHA-1 and **register it too** in Google Cloud Console as a second OAuth client (same package, different SHA-1).
3. Create `android/key.properties` (add to `.gitignore`):
    ```
    storePassword=...
    keyPassword=...
    keyAlias=zwd
    storeFile=C:\\Users\\zedwa\\.zwd-release.jks
    ```
4. Update `android/app/build.gradle.kts` signing block (not done yet; left for release day).
5. `flutter build apk --release`.

## How it works

- **Auth:** `google_sign_in` + Drive read-only scope. Silent re-sign-in on every launch.
- **File tree:** On refresh, app finds `machine docs` folder, resolves 11 named subfolder IDs, lists PDFs in each. Full tree cached in `shared_preferences` so browsing works offline.
- **PDF viewer:** `syncfusion_flutter_pdfviewer` loads from the local cache file. Pinch zoom up to 6x.
- **Offline cache:** First open of any PDF downloads the bytes to `{app docs}/pdfs/{fileId}.pdf`. Future opens read from disk. Green offline indicator on cached files.

## Regenerate icon

```bash
python tools/gen_icon.py
dart run flutter_launcher_icons
```

## Tests

```bash
flutter test
```

Covers folder config sanity (11 folders, correct names, correct colors, root name `machine docs`).
