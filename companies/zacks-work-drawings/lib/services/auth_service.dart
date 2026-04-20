import 'package:google_sign_in/google_sign_in.dart';
import 'package:googleapis/drive/v3.dart' as drive;

class AuthService {
  static final _googleSignIn = GoogleSignIn(
    scopes: const [drive.DriveApi.driveReadonlyScope],
  );

  static GoogleSignInAccount? _currentUser;
  static GoogleSignInAccount? get currentUser => _currentUser;

  static Future<GoogleSignInAccount?> signInSilently() async {
    _currentUser = await _googleSignIn.signInSilently();
    return _currentUser;
  }

  static Future<GoogleSignInAccount?> signIn() async {
    _currentUser = await _googleSignIn.signIn();
    return _currentUser;
  }

  static Future<void> signOut() async {
    await _googleSignIn.signOut();
    _currentUser = null;
  }

  static GoogleSignIn get googleSignIn => _googleSignIn;
}
