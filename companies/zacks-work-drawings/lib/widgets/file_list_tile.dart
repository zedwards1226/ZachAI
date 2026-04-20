import 'package:flutter/material.dart';
import '../models/drive_file.dart';

class FileListTile extends StatelessWidget {
  final DriveFile file;
  final bool isCached;
  final bool showFolder;
  final VoidCallback onTap;

  const FileListTile({
    super.key,
    required this.file,
    required this.isCached,
    required this.onTap,
    this.showFolder = false,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      tileColor: Colors.black,
      onTap: onTap,
      leading: const Icon(Icons.picture_as_pdf, color: Colors.redAccent, size: 32),
      title: Text(
        file.name,
        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: showFolder
          ? Text(
              file.folder,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
            )
          : null,
      trailing: isCached
          ? const Icon(Icons.offline_pin, color: Colors.greenAccent, size: 20)
          : const Icon(Icons.cloud_outlined, color: Colors.white30, size: 20),
    );
  }
}
