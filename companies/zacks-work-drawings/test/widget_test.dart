import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zacks_work_drawings/models/folder_config.dart';

void main() {
  test('kFolders has exactly 11 entries', () {
    expect(kFolders.length, 11);
  });

  test('kFolders contains all required folder names', () {
    final names = kFolders.map((f) => f.name).toSet();
    expect(
      names,
      containsAll(<String>{
        'Line 5',
        'Line 8',
        'Line 9',
        'Line 10',
        'Line 11',
        'Bema',
        'Bundlers',
        'Facial 2',
        'Palletizer Robots',
        'General Drives & Motors',
        'General SOPs',
      }),
    );
  });

  test('kRootFolderName is "machine docs"', () {
    expect(kRootFolderName, 'machine docs');
  });

  test('colors are assigned as specified', () {
    final byName = {for (final f in kFolders) f.name: f.color};
    expect(byName['Line 5'], const Color(0xFFFF9800));
    expect(byName['Line 8'], const Color(0xFF4CAF50));
    expect(byName['Line 9'], const Color(0xFF2196F3));
    expect(byName['Line 10'], const Color(0xFFFFEB3B));
    expect(byName['Line 11'], const Color(0xFFF44336));
    expect(byName['Bema'], const Color(0xFF9C27B0));
    expect(byName['Bundlers'], const Color(0xFF795548));
    expect(byName['Facial 2'], const Color(0xFFFFFFFF));
    expect(byName['Palletizer Robots'], const Color(0xFF009688));
    expect(byName['General Drives & Motors'], const Color(0xFFFF5722));
    expect(byName['General SOPs'], const Color(0xFF8BC34A));
  });
}
