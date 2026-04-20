import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/drive_file.dart';
import '../models/folder_config.dart';
import '../services/cache_service.dart';
import '../services/drive_service.dart';

class LibraryProvider extends ChangeNotifier {
  static const _treeKey = 'library_tree_v1';

  final Map<String, List<DriveFile>> _byFolder = {};
  Set<String> _cachedIds = {};
  bool _loading = false;
  String? _error;
  bool _isOfflineData = false;

  Map<String, List<DriveFile>> get byFolder => _byFolder;
  Set<String> get cachedIds => _cachedIds;
  bool get loading => _loading;
  String? get error => _error;
  bool get isOfflineData => _isOfflineData;

  List<DriveFile> filesForFolder(String folder) => _byFolder[folder] ?? const [];

  int fileCount(String folder) => _byFolder[folder]?.length ?? 0;

  Future<void> init() async {
    await _loadCachedIds();
    await _loadTreeFromCache();
    // Best-effort refresh in background
    unawaited(refresh());
  }

  Future<void> _loadCachedIds() async {
    _cachedIds = await CacheService.cachedFileIds();
  }

  Future<void> _loadTreeFromCache() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_treeKey);
    if (raw == null) return;
    try {
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      _byFolder.clear();
      for (final entry in decoded.entries) {
        final list = (entry.value as List)
            .map((e) => DriveFile.fromJson(Map<String, dynamic>.from(e)))
            .toList();
        _byFolder[entry.key] = list;
      }
      _isOfflineData = true;
      notifyListeners();
    } catch (_) {
      // Ignore corrupt cache
    }
  }

  Future<void> _persistTree() async {
    final prefs = await SharedPreferences.getInstance();
    final map = _byFolder.map(
      (k, v) => MapEntry(k, v.map((f) => f.toJson()).toList()),
    );
    await prefs.setString(_treeKey, jsonEncode(map));
  }

  Future<void> refresh() async {
    if (_loading) return;
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      final rootId = await DriveService.findRootFolderId();
      if (rootId == null) {
        _error =
            'Google Drive folder "$kRootFolderName" not found. Create it and add subfolders.';
        _loading = false;
        notifyListeners();
        return;
      }
      final subIds = await DriveService.resolveSubfolderIds(rootId);
      final next = <String, List<DriveFile>>{};
      for (final cfg in kFolders) {
        final id = subIds[cfg.name];
        if (id == null) {
          next[cfg.name] = const [];
          continue;
        }
        next[cfg.name] = await DriveService.listPdfsInFolder(cfg.name, id);
      }
      _byFolder
        ..clear()
        ..addAll(next);
      _isOfflineData = false;
      await _persistTree();
    } catch (e) {
      _error = 'Could not refresh from Drive: $e';
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  List<DriveFile> search(String query) {
    final q = query.trim().toLowerCase();
    if (q.isEmpty) return const [];
    final out = <DriveFile>[];
    for (final list in _byFolder.values) {
      for (final f in list) {
        if (f.name.toLowerCase().contains(q)) out.add(f);
      }
    }
    out.sort((a, b) => a.name.compareTo(b.name));
    return out;
  }

  void markCached(String fileId) {
    _cachedIds = {..._cachedIds, fileId};
    notifyListeners();
  }
}

