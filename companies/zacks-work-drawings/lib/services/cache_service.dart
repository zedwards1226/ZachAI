import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class CacheService {
  static const _prefsKey = 'cached_files_v1';

  static Future<Directory> _cacheDir() async {
    final docs = await getApplicationDocumentsDirectory();
    final dir = Directory('${docs.path}/pdfs');
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  static Future<Map<String, Map<String, dynamic>>> _readMeta() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_prefsKey);
    if (raw == null) return {};
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    return decoded.map(
      (k, v) => MapEntry(k, Map<String, dynamic>.from(v as Map)),
    );
  }

  static Future<void> _writeMeta(
      Map<String, Map<String, dynamic>> meta) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, jsonEncode(meta));
  }

  static Future<String?> localPathFor(String fileId) async {
    final meta = await _readMeta();
    final entry = meta[fileId];
    if (entry == null) return null;
    final path = entry['path'] as String?;
    if (path == null) return null;
    if (!await File(path).exists()) {
      meta.remove(fileId);
      await _writeMeta(meta);
      return null;
    }
    return path;
  }

  static Future<String> savePdf(String fileId, List<int> bytes) async {
    final dir = await _cacheDir();
    final file = File('${dir.path}/$fileId.pdf');
    await file.writeAsBytes(bytes);
    final meta = await _readMeta();
    meta[fileId] = {
      'path': file.path,
      'cachedAt': DateTime.now().toIso8601String(),
      'sizeBytes': bytes.length,
    };
    await _writeMeta(meta);
    return file.path;
  }

  static Future<Set<String>> cachedFileIds() async {
    final meta = await _readMeta();
    return meta.keys.toSet();
  }

  static Future<void> clearAll() async {
    final dir = await _cacheDir();
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_prefsKey);
  }
}
