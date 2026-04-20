import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'providers/library_provider.dart';
import 'screens/home_screen.dart';
import 'screens/sign_in_screen.dart';
import 'services/auth_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.black,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: Colors.black,
    systemNavigationBarIconBrightness: Brightness.light,
  ));
  runApp(const ZacksWorkDrawingsApp());
}

class ZacksWorkDrawingsApp extends StatelessWidget {
  const ZacksWorkDrawingsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => LibraryProvider(),
      child: MaterialApp(
        title: "Zack's Work Drawings",
        debugShowCheckedModeBanner: false,
        theme: _blackTheme(),
        home: const _Bootstrap(),
      ),
    );
  }
}

ThemeData _blackTheme() {
  final base = ThemeData.dark(useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: Colors.black,
    canvasColor: Colors.black,
    cardColor: Colors.black,
    dialogTheme: const DialogThemeData(backgroundColor: Colors.black),
    colorScheme: base.colorScheme.copyWith(
      surface: Colors.black,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.black,
      foregroundColor: Colors.white,
      elevation: 0,
      systemOverlayStyle: SystemUiOverlayStyle.light,
    ),
    bottomSheetTheme: const BottomSheetThemeData(backgroundColor: Colors.black),
  );
}

class _Bootstrap extends StatefulWidget {
  const _Bootstrap();

  @override
  State<_Bootstrap> createState() => _BootstrapState();
}

class _BootstrapState extends State<_Bootstrap> {
  bool _checking = true;
  bool _authed = false;

  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    final acct = await AuthService.signInSilently();
    if (acct != null) {
      if (!mounted) return;
      await context.read<LibraryProvider>().init();
    }
    if (!mounted) return;
    setState(() {
      _authed = acct != null;
      _checking = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_checking) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.bolt, color: Colors.yellow, size: 64),
              SizedBox(height: 16),
              CircularProgressIndicator(color: Colors.white),
            ],
          ),
        ),
      );
    }
    return _authed ? const HomeScreen() : const SignInScreen();
  }
}
