import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/folder_config.dart';
import '../providers/library_provider.dart';
import '../widgets/folder_tile.dart';
import '../widgets/search_bar_widget.dart';
import 'folder_screen.dart';
import 'search_results_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _searchCtrl = TextEditingController();
  Timer? _debounce;
  String _query = '';

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 150), () {
      setState(() => _query = value);
    });
  }

  void _clearSearch() {
    _searchCtrl.clear();
    _debounce?.cancel();
    setState(() => _query = '');
  }

  @override
  Widget build(BuildContext context) {
    final lib = context.watch<LibraryProvider>();
    final showSearch = _query.trim().isNotEmpty;

    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: RefreshIndicator(
          backgroundColor: Colors.white,
          color: Colors.black,
          onRefresh: () => context.read<LibraryProvider>().refresh(),
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        "Zack's Work Drawings",
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 24,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 12),
                      SearchBarWidget(
                        controller: _searchCtrl,
                        onChanged: _onSearchChanged,
                        onClear: _clearSearch,
                      ),
                      if (lib.loading)
                        const Padding(
                          padding: EdgeInsets.only(top: 12),
                          child: LinearProgressIndicator(
                            minHeight: 2,
                            color: Colors.white54,
                            backgroundColor: Colors.white12,
                          ),
                        ),
                      if (lib.error != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: Text(
                            lib.error!,
                            style: const TextStyle(
                                color: Colors.redAccent, fontSize: 12),
                          ),
                        ),
                      if (lib.isOfflineData && !lib.loading)
                        const Padding(
                          padding: EdgeInsets.only(top: 8),
                          child: Text(
                            'Showing cached list (offline)',
                            style: TextStyle(
                                color: Colors.orangeAccent, fontSize: 12),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              if (showSearch)
                SliverFillRemaining(
                  hasScrollBody: true,
                  child: SearchResultsScreen(query: _query),
                )
              else
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                  sliver: SliverGrid(
                    gridDelegate:
                        const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 2,
                      crossAxisSpacing: 12,
                      mainAxisSpacing: 12,
                      childAspectRatio: 1,
                    ),
                    delegate: SliverChildBuilderDelegate(
                      (context, i) {
                        final folder = kFolders[i];
                        return FolderTile(
                          folder: folder,
                          fileCount: lib.fileCount(folder.name),
                          onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => FolderScreen(folder: folder),
                            ),
                          ),
                        );
                      },
                      childCount: kFolders.length,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
