import 'package:flutter/material.dart';

class FolderConfig {
  final String name;
  final Color color;
  const FolderConfig(this.name, this.color);
}

const List<FolderConfig> kFolders = [
  FolderConfig('Line 5', Color(0xFFFF9800)),
  FolderConfig('Line 8', Color(0xFF4CAF50)),
  FolderConfig('Line 9', Color(0xFF2196F3)),
  FolderConfig('Line 10', Color(0xFFFFEB3B)),
  FolderConfig('Line 11', Color(0xFFF44336)),
  FolderConfig('Bema', Color(0xFF9C27B0)),
  FolderConfig('Bundlers', Color(0xFF795548)),
  FolderConfig('Facial 2', Color(0xFFFFFFFF)),
  FolderConfig('Palletizer Robots', Color(0xFF009688)),
  FolderConfig('General Drives & Motors', Color(0xFFFF5722)),
  FolderConfig('General SOPs', Color(0xFF8BC34A)),
];

const String kRootFolderName = 'machine docs';
