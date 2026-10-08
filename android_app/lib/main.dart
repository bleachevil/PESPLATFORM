import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/login_screen.dart';
import 'screens/shell.dart';
import 'state.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final desk = DeskState(prefs);
  runApp(ManagerDeskApp(desk: desk));
  desk.boot();
}

class ManagerDeskApp extends StatelessWidget {
  const ManagerDeskApp({super.key, required this.desk});
  final DeskState desk;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: desk,
      child: MaterialApp(
        title: 'Manager Desk',
        theme: deskTheme(),
        home: const _Gate(),
      ),
    );
  }
}

class _Gate extends StatelessWidget {
  const _Gate();

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    if (desk.booting) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return desk.signedIn ? const ShellScreen() : const LoginScreen();
  }
}
