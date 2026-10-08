import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

class DeskState extends ChangeNotifier {
  DeskState(this._prefs) {
    api.baseUrl = _prefs.getString('baseUrl') ?? 'http://10.0.2.2:8000';
    api.token = _prefs.getString('token');
    api.leagueSlug = _prefs.getString('leagueSlug');
    googleClientId = _prefs.getString('googleClientId') ?? '';
  }

  final SharedPreferences _prefs;
  final ApiClient api = ApiClient();

  bool booting = true;
  bool busy = false;
  String? error;
  String? notice;
  String googleClientId = '';
  bool googleReady = false;
  Map<String, dynamic>? user;
  Map<String, dynamic>? league;
  Map<String, dynamic>? myTeam;
  Map<String, dynamic>? lastHome;
  List<String> positions = const [];
  int? shellTab;

  bool get signedIn => (api.token ?? '').isNotEmpty && user != null;

  Future<void> boot() async {
    booting = true;
    notifyListeners();
    try {
      await refreshConfig();
      if ((api.token ?? '').isNotEmpty) {
        await refreshMe();
      }
    } catch (err) {
      error = err.toString();
      user = null;
    } finally {
      booting = false;
      notifyListeners();
    }
  }

  Future<void> setBaseUrl(String value) async {
    api.baseUrl = value.trim().replaceAll(RegExp(r'/$'), '');
    await _prefs.setString('baseUrl', api.baseUrl);
    notifyListeners();
  }

  Future<void> refreshConfig() async {
    final config = await api.get('/api/config');
    googleReady = config['google_ready'] == true;
    googleClientId = (config['google_client_id'] ?? '').toString();
    positions = ((config['positions'] as List?) ?? []).map((e) => e.toString()).toList();
    if (googleClientId.isNotEmpty) {
      await _prefs.setString('googleClientId', googleClientId);
    }
  }

  Future<void> refreshMe() async {
    final me = await api.get('/api/me');
    _applyMe(me);
  }

  Future<void> refreshHome() async {
    lastHome = await api.get('/api/home');
    _applyMe(lastHome!);
    notifyListeners();
  }

  void _applyMe(Map<String, dynamic> me) {
    user = me['user'] is Map ? Map<String, dynamic>.from(me['user'] as Map) : null;
    league = me['league'] is Map ? Map<String, dynamic>.from(me['league'] as Map) : null;
    myTeam = me['my_team'] is Map ? Map<String, dynamic>.from(me['my_team'] as Map) : null;
    if (league != null) {
      api.leagueSlug = league!['slug']?.toString();
      _prefs.setString('leagueSlug', api.leagueSlug ?? '');
    }
    lastHome = me;
  }

  Future<void> selectLeague(String slug) async {
    final me = await api.post('/api/me/league', {'slug': slug});
    api.leagueSlug = slug;
    await _prefs.setString('leagueSlug', slug);
    _applyMe(me);
    notifyListeners();
  }

  Future<void> signInWithGoogle() async {
    error = null;
    busy = true;
    notifyListeners();
    try {
      await refreshConfig();
      if (!googleReady || googleClientId.isEmpty) {
        throw ApiException('Google sign-in is not connected on the server.');
      }
      final google = GoogleSignIn(
        serverClientId: googleClientId,
        scopes: const ['email', 'profile'],
      );
      final account = await google.signIn();
      if (account == null) {
        throw ApiException('Google sign-in was cancelled');
      }
      final auth = await account.authentication;
      final idToken = auth.idToken;
      if (idToken == null || idToken.isEmpty) {
        throw ApiException('Google did not return an ID token. Add the web client ID as serverClientId.');
      }
      final result = await api.post('/api/auth/google', {'id_token': idToken});
      api.token = result['token']?.toString();
      user = result['user'] is Map ? Map<String, dynamic>.from(result['user'] as Map) : null;
      await _prefs.setString('token', api.token ?? '');
      await refreshMe();
    } catch (err) {
      error = err.toString();
      rethrow;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    try {
      await api.post('/api/auth/logout');
    } catch (_) {}
    try {
      await GoogleSignIn().signOut();
    } catch (_) {}
    api.token = null;
    user = null;
    myTeam = null;
    await _prefs.remove('token');
    notifyListeners();
  }

  void flash(String message) {
    notice = message;
    error = null;
    notifyListeners();
  }

  void fail(Object err) {
    error = err.toString();
    notifyListeners();
  }

  void clearMessages() {
    error = null;
    notice = null;
    notifyListeners();
  }

  void goToMarket() {
    shellTab = myTeam != null ? 2 : 1;
    notifyListeners();
  }

  void clearShellTab() {
    shellTab = null;
  }
}
