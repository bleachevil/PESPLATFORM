import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late final TextEditingController _url;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: context.read<DeskState>().api.baseUrl);
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _saveUrl() async {
    final desk = context.read<DeskState>();
    await desk.setBaseUrl(_url.text);
    try {
      await desk.refreshConfig();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Server saved')));
    } catch (err) {
      desk.fail(err);
    }
  }

  Future<void> _signIn() async {
    final desk = context.read<DeskState>();
    await desk.setBaseUrl(_url.text);
    try {
      await desk.signInWithGoogle();
    } catch (err) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err.toString())));
    }
  }

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 24),
            const Text('MANAGER DESK', style: TextStyle(letterSpacing: 2, fontWeight: FontWeight.w800, color: deskMuted)),
            const SizedBox(height: 8),
            const Text('Run the club here.\nPlay the match in eFootball.', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, height: 1.2)),
            const SizedBox(height: 24),
            NoticeBanner(error: desk.error, notice: desk.notice),
            TextField(
              controller: _url,
              decoration: const InputDecoration(
                labelText: 'API server',
                hintText: 'http://192.168.1.10:8000',
                helperText: 'Emulator: http://10.0.2.2:8000  ·  Phone: your PC LAN IP',
              ),
              keyboardType: TextInputType.url,
              onSubmitted: (_) => _saveUrl(),
            ),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: desk.busy ? null : _saveUrl, child: const Text('Save server')),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: desk.busy ? null : _signIn,
              icon: desk.busy
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.login),
              label: const Text('Sign in with Google'),
            ),
            const SizedBox(height: 12),
            Text(
              desk.googleReady
                  ? 'Google is connected on this server.'
                  : 'Connect Google OAuth on the server (web client ID + Android client ID) before phones can sign in.',
              style: const TextStyle(color: deskMuted),
            ),
          ],
        ),
      ),
    );
  }
}
