import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api.dart';
import '../state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'player_screen.dart';

class SquadScreen extends StatefulWidget {
  const SquadScreen({super.key});

  @override
  State<SquadScreen> createState() => _SquadScreenState();
}

class _SquadScreenState extends State<SquadScreen> {
  Map<String, dynamic> data = {};
  bool loading = true;
  String? errorMessage;
  final _clauses = <String, TextEditingController>{};
  final _fees = <String, TextEditingController>{};
  final _toTeam = <String, int>{};
  final _kind = <String, String>{};

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final c in [..._clauses.values, ..._fees.values]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    final desk = context.read<DeskState>();
    setState(() {
      loading = true;
      errorMessage = null;
    });
    try {
      data = await desk.api.get('/api/squad');
      await desk.refreshMe();
    } on ApiException catch (err) {
      errorMessage = err.message;
    } catch (err) {
      errorMessage = err.toString();
      desk.fail(err);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _act(Future<Map<String, dynamic>> Function() action) async {
    final desk = context.read<DeskState>();
    try {
      final result = await action();
      desk.flash(result['message']?.toString() ?? 'Saved');
      await _load();
    } catch (err) {
      desk.fail(err);
    }
  }

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    if (errorMessage != null && errorMessage!.contains('Register a club')) {
      return Scaffold(
        appBar: AppBar(title: const Text('Squad')),
        body: const EmptyText('Register a club in a league first.'),
      );
    }
    if (errorMessage != null && (errorMessage!.contains('Pick a league') || errorMessage!.contains('Sign in'))) {
      return Scaffold(
        appBar: AppBar(title: const Text('Squad')),
        body: EmptyText(errorMessage!),
      );
    }
    final players = mapList(data['players']);
    final others = mapList(data['other_teams']);
    final team = data['my_team'] is Map ? Map<String, dynamic>.from(data['my_team'] as Map) : desk.myTeam;
    return Scaffold(
      appBar: AppBar(title: Text(team?['name']?.toString() ?? 'Squad')),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  NoticeBanner(error: desk.error, notice: desk.notice),
                  Text('Budget ${team?['budget'] ?? 0}M · ${players.length} contracted players', style: const TextStyle(color: deskMuted)),
                  const SizedBox(height: 8),
                  if (players.isEmpty) const EmptyText('Empty books. Open the market when a sea window is on.'),
                  ...players.map((p) {
                    final pid = p['pid'].toString();
                    _clauses.putIfAbsent(pid, () => TextEditingController());
                    _fees.putIfAbsent(pid, () => TextEditingController());
                    return Card(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: Column(
                          children: [
                            PlayerTile(
                              api: desk.api,
                              player: p,
                              trailing: Text('${p['fee'] ?? p['market_price'] ?? 0}M'),
                              onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => PlayerScreen(slug: p['slug']?.toString() ?? pid))),
                            ),
                            if (data['sea_release_window'] != null)
                              Align(
                                alignment: Alignment.centerRight,
                                child: TextButton(
                                  onPressed: () => _act(() => desk.api.post('/api/squad/release', {'pid': pid})),
                                  child: const Text('Release to sea'),
                                ),
                              ),
                            if (data['clause_window'] != null)
                              Row(
                                children: [
                                  Expanded(child: TextField(controller: _clauses[pid], decoration: const InputDecoration(labelText: 'Clause'), keyboardType: TextInputType.number)),
                                  const SizedBox(width: 8),
                                  FilledButton(
                                    onPressed: () => _act(() => desk.api.post('/api/squad/clause', {
                                          'pid': pid,
                                          'clause': int.tryParse(_clauses[pid]!.text) ?? 0,
                                        })),
                                    child: const Text('Set clause'),
                                  ),
                                ],
                              ),
                            if (data['transfer_window'] != null && others.isNotEmpty) ...[
                              const SizedBox(height: 8),
                              Row(
                                children: [
                                  Expanded(
                                    child: DropdownButtonFormField<int>(
                                      initialValue: _toTeam[pid],
                                      decoration: const InputDecoration(labelText: 'To club'),
                                      items: others.map((t) => DropdownMenuItem(value: mapInt(t, 'id'), child: Text(t['name']?.toString() ?? ''))).toList(),
                                      onChanged: (v) => setState(() => _toTeam[pid] = v ?? 0),
                                    ),
                                  ),
                                ],
                              ),
                              Row(
                                children: [
                                  Expanded(child: TextField(controller: _fees[pid], decoration: const InputDecoration(labelText: 'Fee'), keyboardType: TextInputType.number)),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: DropdownButtonFormField<String>(
                                      initialValue: _kind[pid] ?? 'transfer',
                                      items: const [
                                        DropdownMenuItem(value: 'transfer', child: Text('Transfer')),
                                        DropdownMenuItem(value: 'loan', child: Text('Loan')),
                                      ],
                                      onChanged: (v) => setState(() => _kind[pid] = v ?? 'transfer'),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  FilledButton(
                                    onPressed: _toTeam[pid] == null
                                        ? null
                                        : () => _act(() => desk.api.post('/api/squad/offer', {
                                              'pid': pid,
                                              'to_team_id': _toTeam[pid],
                                              'fee': int.tryParse(_fees[pid]!.text) ?? 0,
                                              'kind': _kind[pid] ?? 'transfer',
                                            })),
                                    child: const Text('Offer'),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),
                    );
                  }),
                ],
              ),
            ),
    );
  }
}
