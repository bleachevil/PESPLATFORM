import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'catalog_screen.dart';
import 'league_detail_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final desk = context.read<DeskState>();
      try {
        await desk.refreshHome();
      } catch (err) {
        if (!mounted) return;
        desk.fail(err);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    final home = desk.lastHome ?? {};
    final stats = home['stats'] is Map ? Map<String, dynamic>.from(home['stats'] as Map) : {};
    final window = home['window'] is Map ? Map<String, dynamic>.from(home['window'] as Map) : null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Manager Desk'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const SettingsScreen())),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => desk.refreshHome(),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            NoticeBanner(error: desk.error, notice: desk.notice),
            Text('eFootball · manager league', style: Theme.of(context).textTheme.labelLarge?.copyWith(color: deskGold)),
            const SizedBox(height: 8),
            Text('Hello ${desk.user?['name'] ?? 'manager'}', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(desk.league?['name']?.toString() ?? 'This desk', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 12),
                    _row('Players', '${stats['players'] ?? 0} players'),
                    if (desk.league != null) ...[
                      _row('Season', '${desk.league?['weeks'] ?? 6} weeks · ${desk.league?['start_on'] ?? '—'} → ${desk.league?['end_on'] ?? '—'}'),
                      _row('Window', window?['title']?.toString() ?? 'None open'),
                    ],
                    if (desk.myTeam != null) ...[
                      _row('Club', desk.myTeam?['name']?.toString() ?? ''),
                      _row('Budget', '${desk.myTeam?['budget'] ?? 0}M'),
                    ],
                    if (desk.league == null) _row('Leagues', '${home['league_count'] ?? 0} open'),
                    const SizedBox(height: 12),
                    if (desk.league != null)
                      FilledButton(
                        onPressed: () => Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => LeagueDetailScreen(slug: desk.league!['slug'].toString())),
                        ),
                        child: const Text('League home'),
                      ),
                    if (desk.myTeam != null) ...[
                      const SizedBox(height: 8),
                      FilledButton(
                        onPressed: () => desk.goToMarket(),
                        child: const Text('Open market'),
                      ),
                    ] else ...[
                      const SizedBox(height: 8),
                      OutlinedButton(
                        onPressed: () => Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => const CatalogScreen()),
                        ),
                        child: const Text('Browse players'),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(width: 88, child: Text(label, style: const TextStyle(color: deskMuted))),
          Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }
}
