import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/library_provider.dart';
import '../widgets/file_list_tile.dart';
import 'pdf_viewer_screen.dart';

class SearchResultsScreen extends StatelessWidget {
  final String query;
  const SearchResultsScreen({super.key, required this.query});

  @override
  Widget build(BuildContext context) {
    final lib = context.watch<LibraryProvider>();
    final results = lib.search(query);

    if (results.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            'No files match "$query"',
            style: const TextStyle(color: Colors.white54),
          ),
        ),
      );
    }

    return ListView.separated(
      itemCount: results.length,
      separatorBuilder: (_, __) =>
          Divider(color: Colors.white.withValues(alpha: 0.08), height: 1),
      itemBuilder: (context, i) {
        final f = results[i];
        return FileListTile(
          file: f,
          isCached: lib.cachedIds.contains(f.id),
          showFolder: true,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => PdfViewerScreen(file: f)),
          ),
        );
      },
    );
  }
}
