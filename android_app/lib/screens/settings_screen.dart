import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
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

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          NoticeBanner(error: desk.error, notice: desk.notice),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(desk.user?['name']?.toString() ?? ''),
            subtitle: Text(desk.user?['email']?.toString() ?? ''),
          ),
          TextField(
            controller: _url,
            decoration: const InputDecoration(
              labelText: 'API server',
              helperText: 'Phones cannot use 127.0.0.1. Use the PC LAN IP, or 10.0.2.2 on the emulator.',
            ),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: () async {
              await desk.setBaseUrl(_url.text);
              try {
                await desk.refreshConfig();
                desk.flash('Server saved');
              } catch (err) {
                desk.fail(err);
              }
            },
            child: const Text('Save server'),
          ),
          const SizedBox(height: 24),
          const Text('LAN testing', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          const Text(
            'On the PC run:\n'
            'python -m uvicorn web.app:app --reload --host 0.0.0.0 --port 8000\n\n'
            'Google Cloud Console needs an Android OAuth client for\n'
            'com.pesdata.manager_desk plus the debug SHA-1, in the same project as the web client ID.',
            style: TextStyle(color: deskMuted, height: 1.4),
          ),
          const SizedBox(height: 24),
          OutlinedButton(
            onPressed: () async {
              await desk.logout();
              if (context.mounted) Navigator.pop(context);
            },
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
  }
}
