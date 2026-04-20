class DriveFile {
  final String id;
  final String name;
  final String folder;
  final int? sizeBytes;
  final DateTime? modifiedTime;

  const DriveFile({
    required this.id,
    required this.name,
    required this.folder,
    this.sizeBytes,
    this.modifiedTime,
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'folder': folder,
        'sizeBytes': sizeBytes,
        'modifiedTime': modifiedTime?.toIso8601String(),
      };

  factory DriveFile.fromJson(Map<String, dynamic> json) => DriveFile(
        id: json['id'] as String,
        name: json['name'] as String,
        folder: json['folder'] as String,
        sizeBytes: json['sizeBytes'] as int?,
        modifiedTime: json['modifiedTime'] != null
            ? DateTime.parse(json['modifiedTime'] as String)
            : null,
      );
}
