import 'dart:async';
import 'package:extension_google_sign_in_as_googleapis_auth/extension_google_sign_in_as_googleapis_auth.dart';
import 'package:googleapis/drive/v3.dart' as drive;
import 'auth_service.dart';
import '../models/drive_file.dart';
import '../models/folder_config.dart';

class DriveService {
  static Future<drive.DriveApi?> _api() async {
    final user = AuthService.currentUser;
    if (user == null) return null;
    final client = await AuthService.googleSignIn.authenticatedClient();
    if (client == null) return null;
    return drive.DriveApi(client);
  }

  static Future<String?> findRootFolderId() async {
    final api = await _api();
    if (api == null) return null;
    final res = await api.files.list(
      q: "name = '$kRootFolderName' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
      $fields: 'files(id,name)',
      spaces: 'drive',
    );
    final files = res.files ?? [];
    if (files.isEmpty) return null;
    return files.first.id;
  }

  static Future<Map<String, String>> resolveSubfolderIds(String rootId) async {
    final api = await _api();
    if (api == null) return {};
    final res = await api.files.list(
      q: "'$rootId' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
      $fields: 'files(id,name)',
      pageSize: 100,
      spaces: 'drive',
    );
    final map = <String, String>{};
    for (final f in res.files ?? <drive.File>[]) {
      if (f.id != null && f.name != null) {
        map[f.name!] = f.id!;
      }
    }
    return map;
  }

  static Future<List<DriveFile>> listPdfsInFolder(
      String folderName, String folderId) async {
    final api = await _api();
    if (api == null) return [];
    final files = <DriveFile>[];
    String? pageToken;
    do {
      final res = await api.files.list(
        q: "'$folderId' in parents and mimeType = 'application/pdf' and trashed = false",
        $fields: 'nextPageToken, files(id,name,size,modifiedTime)',
        pageSize: 200,
        pageToken: pageToken,
        spaces: 'drive',
      );
      for (final f in res.files ?? <drive.File>[]) {
        if (f.id == null || f.name == null) continue;
        files.add(DriveFile(
          id: f.id!,
          name: f.name!,
          folder: folderName,
          sizeBytes: int.tryParse(f.size ?? ''),
          modifiedTime: f.modifiedTime,
        ));
      }
      pageToken = res.nextPageToken;
    } while (pageToken != null);
    return files;
  }

  static Future<List<int>> downloadPdfBytes(String fileId) async {
    final api = await _api();
    if (api == null) throw StateError('Not authenticated');
    final media = await api.files.get(
      fileId,
      downloadOptions: drive.DownloadOptions.fullMedia,
    ) as drive.Media;
    final bytes = <int>[];
    await for (final chunk in media.stream) {
      bytes.addAll(chunk);
    }
    return bytes;
  }
}
