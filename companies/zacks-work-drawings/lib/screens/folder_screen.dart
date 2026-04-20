import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/folder_config.dart';
import '../providers/library_provider.dart';
import '../widgets/file_list_tile.dart';
import 'pdf_viewer_screen.dart';

class FolderScreen extends StatelessWidget {
  final FolderConfig folder;
  const FolderScreen({super.key, required this.folder});

  @override
  Widget build(BuildContext context) {
    final lib = context.watch<LibraryProvider>();
    final files = lib.filesForFolder(folder.name);

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        elevation: 0,
        title: Row(
          children: [
            Container(
              width: 14,
              height: 14,
              decoration: BoxDecoration(
                color: folder.color,
                borderRadius: BorderRadius.circular(3),
              ),
            ),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                folder.name,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
      body: files.isEmpty
          ? const Center(
              child: Text(
                'No PDFs in this folder.',
                style: TextStyle(color: Colors.white54),
              ),
            )
          : ListView.separated(
              itemCount: files.length,
              separatorBuilder: (_, __) =>
                  Divider(color: Colors.white.withValues(alpha: 0.08), height: 1),
              itemBuilder: (context, i) {
                final f = files[i];
                return FileListTile(
                  file: f,
                  isCached: lib.cachedIds.contains(f.id),
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => PdfViewerScreen(file: f),
                    ),
                  ),
                );
              },
            ),
    );
  }
}
