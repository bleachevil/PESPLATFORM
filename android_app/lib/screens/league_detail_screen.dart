import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'organize_screen.dart';

class LeagueDetailScreen extends StatefulWidget {
  const LeagueDetailScreen({super.key, required this.slug});
  final String slug;

  @override
  State<LeagueDetailScreen> createState() => _LeagueDetailScreenState();
}

class _LeagueDetailScreenState extends State<LeagueDetailScreen> {
  Map<String, dynamic> data = {};
  bool loading = true;
  String comp = '';
  final _club = TextEditingController();
  final _homeGoals = <int, TextEditingController>{};
  final _awayGoals = <int, TextEditingController>{};
  int? homeTeamId;
  int? awayTeamId;
  final _kickoff = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _club.dispose();
    _kickoff.dispose();
    for (final c in [..._homeGoals.values, ..._awayGoals.values]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    final desk = context.read<DeskState>();
    setState(() => loading = true);
    try {
      data = await desk.api.get('/api/league/${widget.slug}', query: {if (comp.isNotEmpty) 'comp': comp});
      await desk.selectLeague(widget.slug);
    } catch (err) {
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
    final league = data['league'] is Map ? Map<String, dynamic>.from(data['league'] as Map) : null;
    final competitions = mapList(data['competitions']);
    final current = data['current'] is Map ? Map<String, dynamic>.from(data['current'] as Map) : null;
    final table = mapList(data['table']);
    final results = mapList(data['results']);
    final upcoming = mapList(data['upcoming']);
    final teams = mapList(data['teams']);
    final inbox = mapList(data['inbox']);
    final calendar = mapList(data['calendar']);
    final myRequest = data['my_request'] is Map ? Map<String, dynamic>.from(data['my_request'] as Map) : null;
    final canManage = data['can_manage'] == true;
    final opens = mapList(data['opens']);

    return Scaffold(
      appBar: AppBar(
        title: Text(league?['name']?.toString() ?? 'League'),
        actions: [
          if (canManage)
            IconButton(
              icon: const Icon(Icons.tune),
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => OrganizeScreen(slug: widget.slug))).then((_) => _load()),
            ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  NoticeBanner(error: desk.error, notice: desk.notice),
                  Text('${league?['weeks'] ?? 6} weeks · ${league?['start_on'] ?? '—'} → ${league?['end_on'] ?? '—'} · ${teams.length}/${league?['max_teams'] ?? 0} clubs', style: const TextStyle(color: deskMuted)),
                  if (opens.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text('Open now: ${opens.map((w) => w['title']).join(' · ')}', style: const TextStyle(color: deskGreen)),
                    ),
                  const SizedBox(height: 12),
                  if (desk.user != null && desk.myTeam == null && myRequest?['kind'] == 'invite')
                    FilledButton(
                      onPressed: () async {
                        try {
                          final result = await desk.api.post('/api/league/${widget.slug}/invite/accept');
                          desk.flash(result['message']?.toString() ?? 'You are in the league. Open the market to sign available players.');
                          await desk.selectLeague(widget.slug);
                          if (!context.mounted) return;
                          desk.goToMarket();
                          Navigator.popUntil(context, (route) => route.isFirst);
                        } catch (err) {
                          desk.fail(err);
                        }
                      },
                      child: Text('Accept invitation · ${myRequest?['team_name'] ?? ''}'),
                    )
                  else if (desk.user != null && desk.myTeam == null && myRequest != null)
                    const StatusChip('Join request waiting for approval', code: 'sea')
                  else if (desk.user != null && desk.myTeam == null)
                    Row(
                      children: [
                        Expanded(child: TextField(controller: _club, decoration: const InputDecoration(hintText: 'Club name'))),
                        const SizedBox(width: 8),
                        FilledButton(
                          onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/join', {'team_name': _club.text.trim()})),
                          child: const Text('Ask to join'),
                        ),
                      ],
                    ),
                  const SizedBox(height: 16),
                  if (competitions.isNotEmpty)
                    SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children: competitions.map((c) {
                          final on = current != null && c['id'] == current['id'];
                          return Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text(c['name']?.toString() ?? ''),
                              selected: on,
                              onSelected: (_) {
                                setState(() => comp = c['slug']?.toString() ?? '');
                                _load();
                              },
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                  const SizedBox(height: 12),
                  const Text('Table', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  if (table.isEmpty) const EmptyText('No clubs in this competition yet.') else _standings(table),
                  const SizedBox(height: 16),
                  const Text('Results', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  ...results.map((m) => ListTile(
                        title: Text('${m['home_label']} ${m['score_label']} ${m['away_label']}'),
                        subtitle: Text(m['kickoff']?.toString() ?? ''),
                      )),
                  if (results.isEmpty) const EmptyText('No results yet.'),
                  const SizedBox(height: 16),
                  const Text('Matches', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  ...upcoming.map((m) {
                    final id = mapInt(m, 'id');
                    _homeGoals.putIfAbsent(id, () => TextEditingController());
                    _awayGoals.putIfAbsent(id, () => TextEditingController());
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${m['home_label']} VS ${m['away_label']}', style: const TextStyle(fontWeight: FontWeight.w600)),
                            Text(m['kickoff']?.toString() ?? '', style: const TextStyle(color: deskMuted)),
                            if (canManage) ...[
                              const SizedBox(height: 8),
                              Row(
                                children: [
                                  Expanded(child: TextField(controller: _homeGoals[id], decoration: const InputDecoration(labelText: 'Home'), keyboardType: TextInputType.number)),
                                  const SizedBox(width: 8),
                                  Expanded(child: TextField(controller: _awayGoals[id], decoration: const InputDecoration(labelText: 'Away'), keyboardType: TextInputType.number)),
                                  const SizedBox(width: 8),
                                  FilledButton(
                                    onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/fixtures/$id/result', {
                                          'home_goals': int.tryParse(_homeGoals[id]!.text) ?? 0,
                                          'away_goals': int.tryParse(_awayGoals[id]!.text) ?? 0,
                                        })),
                                    child: const Text('Save'),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),
                    );
                  }),
                  if (upcoming.isEmpty) const EmptyText('No upcoming matches.'),
                  if (canManage && current != null) ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<int>(
                      initialValue: homeTeamId,
                      decoration: const InputDecoration(labelText: 'Home'),
                      items: teams.map((t) => DropdownMenuItem(value: mapInt(t, 'id'), child: Text('${t['manager_name']} - ${t['name']}'))).toList(),
                      onChanged: (v) => setState(() => homeTeamId = v),
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<int>(
                      initialValue: awayTeamId,
                      decoration: const InputDecoration(labelText: 'Away'),
                      items: teams.map((t) => DropdownMenuItem(value: mapInt(t, 'id'), child: Text('${t['manager_name']} - ${t['name']}'))).toList(),
                      onChanged: (v) => setState(() => awayTeamId = v),
                    ),
                    const SizedBox(height: 8),
                    TextField(controller: _kickoff, decoration: const InputDecoration(labelText: 'Kickoff (YYYY-MM-DD HH:MM)')),
                    const SizedBox(height: 8),
                    FilledButton(
                      onPressed: homeTeamId == null || awayTeamId == null
                          ? null
                          : () => _act(() => desk.api.post('/api/league/${widget.slug}/competitions/${current['id']}/match', {
                                'home_team_id': homeTeamId,
                                'away_team_id': awayTeamId,
                                'kickoff': _kickoff.text.trim(),
                              })),
                      child: const Text('Add one-off match'),
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton(
                      onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/competitions/${current['id']}/fixtures')),
                      child: const Text('Build home-and-away fixtures'),
                    ),
                  ],
                  const SizedBox(height: 16),
                  const Text('Clubs', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  ...teams.map((t) => ListTile(
                        title: Text(t['name']?.toString() ?? ''),
                        subtitle: Text(t['manager_name']?.toString() ?? ''),
                        trailing: Text('${t['budget'] ?? 0}M · ${t['squad_count'] ?? 0}'),
                      )),
                  if (inbox.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    const Text('Incoming offers', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    ...inbox.map((o) => ListTile(
                          title: Text('${o['player_name']} from ${o['from_name']}'),
                          subtitle: Text('${o['fee']}M · ${o['kind']}'),
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              TextButton(onPressed: () => _act(() => desk.api.post('/api/offers/${o['id']}/decide', {'accept': true})), child: const Text('Accept')),
                              TextButton(onPressed: () => _act(() => desk.api.post('/api/offers/${o['id']}/decide', {'accept': false})), child: const Text('Reject')),
                            ],
                          ),
                        )),
                  ],
                  const SizedBox(height: 16),
                  const Text('Season calendar', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  ...calendar.expand((group) {
                    final rows = mapList(group['rows']);
                    return [
                      Padding(
                        padding: const EdgeInsets.only(top: 12, bottom: 4),
                        child: Text(group['label']?.toString() ?? '', style: const TextStyle(color: deskGold, fontWeight: FontWeight.w700)),
                      ),
                      ...rows.map((w) => ListTile(
                            dense: true,
                            title: Text(w['activity']?.toString() ?? w['title']?.toString() ?? ''),
                            subtitle: Text('${w['period'] ?? ''} · ${w['when_label'] ?? ''}'),
                            trailing: w['is_open'] == true ? const StatusChip('Open', code: 'free') : null,
                          )),
                    ];
                  }),
                ],
              ),
            ),
    );
  }

  Widget _standings(List<Map<String, dynamic>> table) {
    return Card(
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: const [
            DataColumn(label: Text('#')),
            DataColumn(label: Text('Club')),
            DataColumn(label: Text('GP')),
            DataColumn(label: Text('W')),
            DataColumn(label: Text('T')),
            DataColumn(label: Text('L')),
            DataColumn(label: Text('PTS')),
          ],
          rows: table
              .map(
                (row) => DataRow(
                  cells: [
                    DataCell(Text('${row['rank'] ?? ''}')),
                    DataCell(Text(row['label']?.toString() ?? '')),
                    DataCell(Text('${row['gp'] ?? 0}')),
                    DataCell(Text('${row['w'] ?? 0}')),
                    DataCell(Text('${row['t'] ?? 0}')),
                    DataCell(Text('${row['l'] ?? 0}')),
                    DataCell(Text('${row['pts'] ?? 0}')),
                  ],
                ),
              )
              .toList(),
        ),
      ),
    );
  }
}
