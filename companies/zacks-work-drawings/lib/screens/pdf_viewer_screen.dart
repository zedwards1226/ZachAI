import 'dart:io';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:syncfusion_flutter_pdfviewer/pdfviewer.dart';
import '../models/drive_file.dart';
import '../providers/library_provider.dart';
import '../services/cache_service.dart';
import '../services/drive_service.dart';

class PdfViewerScreen extends StatefulWidget {
  final DriveFile file;
  const PdfViewerScreen({super.key, required this.file});

  @override
  State<PdfViewerScreen> createState() => _PdfViewerScreenState();
}

class _PdfViewerScreenState extends State<PdfViewerScreen> {
  String? _localPath;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final cached = await CacheService.localPathFor(widget.file.id);
      if (cached != null) {
        if (!mounted) return;
        setState(() {
          _localPath = cached;
          _loading = false;
        });
        return;
      }
      final bytes = await DriveService.downloadPdfBytes(widget.file.id);
      final path = await CacheService.savePdf(widget.file.id, bytes);
      if (!mounted) return;
      context.read<LibraryProvider>().markCached(widget.file.id);
      setState(() {
        _localPath = path;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not open PDF: $e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        elevation: 0,
        title: Text(
          widget.file.name,
          style: const TextStyle(fontSize: 14),
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(
        child: CircularProgressIndicator(color: Colors.white),
      );
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(_error!,
              style: const TextStyle(color: Colors.redAccent)),
        ),
      );
    }
    if (_localPath == null) {
      return const Center(
        child: Text('No PDF loaded', style: TextStyle(color: Colors.white54)),
      );
    }
    return SfPdfViewer.file(
      File(_localPath!),
      enableDoubleTapZooming: true,
      maxZoomLevel: 6,
      canShowScrollHead: true,
      canShowScrollStatus: true,
    );
  }
}
