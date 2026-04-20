import 'package:flutter/material.dart';
import '../models/folder_config.dart';

class FolderTile extends StatelessWidget {
  final FolderConfig folder;
  final int fileCount;
  final VoidCallback onTap;

  const FolderTile({
    super.key,
    required this.folder,
    required this.fileCount,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final brightness = ThemeData.estimateBrightnessForColor(folder.color);
    final fg = brightness == Brightness.dark ? Colors.white : Colors.black;

    return Material(
      color: folder.color,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.folder_rounded, color: fg, size: 32),
              const Spacer(),
              Text(
                folder.name,
                style: TextStyle(
                  color: fg,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                '$fileCount file${fileCount == 1 ? '' : 's'}',
                style: TextStyle(color: fg.withValues(alpha: 0.75), fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
