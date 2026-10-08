import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'league_detail_screen.dart';

class LeaguesScreen extends StatefulWidget {
  const LeaguesScreen({super.key});

  @override
  State<LeaguesScreen> createState() => _LeaguesScreenState();
}

class _LeaguesScreenState extends State<LeaguesScreen> {
  List<Map<String, dynamic>> leagues = [];
  Map<String, dynamic> pending = {};
  bool loading = true;
  final _name = TextEditingController();
  final _maxTeams = TextEditingController(text: '16');
  final _weeks = TextEditingController(text: '6');
  final Map<String, TextEditingController> _joins = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _name.dispose();
    _maxTeams.dispose();
    _weeks.dispose();
    for (final c in _joins.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    final desk = context.read<DeskState>();
    setState(() => loading = true);
    try {
      final data = await desk.api.get('/api/leagues');
      leagues = mapList(data['leagues']);
      pending = data['pending'] is Map ? Map<String, dynamic>.from(data['pending'] as Map) : {};
      desk.error = null;
    } catch (err) {
      desk.fail(err);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _create() async {
    final desk = context.read<DeskState>();
    try {
      final result = await desk.api.post('/api/leagues', {
        'name': _name.text.trim(),
        'max_teams': int.tryParse(_maxTeams.text) ?? 16,
        'weeks': int.tryParse(_weeks.text) ?? 6,
      });
      final league = Map<String, dynamic>.from(result['league'] as Map);
      await desk.selectLeague(league['slug'].toString());
      if (!mounted) return;
      Navigator.push(context, MaterialPageRoute(builder: (_) => LeagueDetailScreen(slug: league['slug'].toString())));
    } catch (err) {
      desk.fail(err);
    }
  }

  Future<void> _join(Map<String, dynamic> league) async {
    final desk = context.read<DeskState>();
    final slug = league['slug'].toString();
    final club = _joins.putIfAbsent(slug, () => TextEditingController());
    try {
      final result = await desk.api.post('/api/league/$slug/join', {'team_name': club.text.trim()});
      desk.flash(result['message']?.toString() ?? 'Join request sent');
      await desk.selectLeague(slug);
      await _load();
    } catch (err) {
      desk.fail(err);
    }
  }

  Future<void> _accept(String slug) async {
    final desk = context.read<DeskState>();
    try {
      final result = await desk.api.post('/api/league/$slug/invite/accept');
      desk.flash(result['message']?.toString() ?? 'You are in the league. Open the market to sign available players.');
      await desk.selectLeague(slug);
      desk.goToMarket();
    } catch (err) {
      desk.fail(err);
    }
  }

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Leagues')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            NoticeBanner(error: desk.error, notice: desk.notice),
            const Text('Join a friend’s league or open one as host.', style: TextStyle(color: deskMuted)),
            const SizedBox(height: 16),
            if (loading) const Center(child: CircularProgressIndicator()),
            ...leagues.map((league) {
              final id = league['id'].toString();
              final req = pending[id] is Map ? Map<String, dynamic>.from(pending[id] as Map) : null;
              final slug = league['slug'].toString();
              final club = _joins.putIfAbsent(slug, () => TextEditingController());
              return Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(league['name']?.toString() ?? ''),
                        subtitle: Text('${league['weeks'] ?? 6} weeks · ${league['team_count'] ?? 0}/${league['max_teams'] ?? 0} clubs'),
                        trailing: StatusChip(league['status']?.toString() ?? 'open'),
                        onTap: () async {
                          await desk.selectLeague(slug);
                          if (!context.mounted) return;
                          Navigator.push(context, MaterialPageRoute(builder: (_) => LeagueDetailScreen(slug: slug)));
                        },
                      ),
                      if (req?['kind'] == 'invite')
                        FilledButton(onPressed: () => _accept(slug), child: const Text('Accept invite'))
                      else if (req != null)
                        const StatusChip('Waiting for approval', code: 'sea')
                      else
                        Row(
                          children: [
                            Expanded(
                              child: TextField(
                                controller: club,
                                decoration: const InputDecoration(hintText: 'Your club name'),
                              ),
                            ),
                            const SizedBox(width: 8),
                            FilledButton(onPressed: () => _join(league), child: const Text('Ask to join')),
                          ],
                        ),
                    ],
                  ),
                ),
              );
            }),
            const SizedBox(height: 16),
            const Text('Create a league', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            TextField(controller: _name, decoration: const InputDecoration(labelText: 'League name')),
            const SizedBox(height: 8),
            TextField(controller: _maxTeams, decoration: const InputDecoration(labelText: 'Max players'), keyboardType: TextInputType.number),
            const SizedBox(height: 8),
            TextField(controller: _weeks, decoration: const InputDecoration(labelText: 'Number of weeks'), keyboardType: TextInputType.number),
            const SizedBox(height: 12),
            FilledButton(onPressed: _create, child: const Text('Create league')),
          ],
        ),
      ),
    );
  }
}
