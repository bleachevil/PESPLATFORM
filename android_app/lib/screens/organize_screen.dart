import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';

class OrganizeScreen extends StatefulWidget {
  const OrganizeScreen({super.key, required this.slug});
  final String slug;

  @override
  State<OrganizeScreen> createState() => _OrganizeScreenState();
}

class _OrganizeScreenState extends State<OrganizeScreen> {
  Map<String, dynamic> data = {};
  bool loading = true;
  final _inviteEmail = TextEditingController();
  final _inviteClub = TextEditingController();
  final _officerEmail = TextEditingController();
  final _leagueName = TextEditingController();
  final _maxTeams = TextEditingController();
  final _weeks = TextEditingController();
  final _startOn = TextEditingController();
  String status = 'open';
  String compKind = 'division';
  final _compName = TextEditingController();
  final _windowStart = <int, TextEditingController>{};
  final _windowEnd = <int, TextEditingController>{};

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _inviteEmail.dispose();
    _inviteClub.dispose();
    _officerEmail.dispose();
    _leagueName.dispose();
    _maxTeams.dispose();
    _weeks.dispose();
    _startOn.dispose();
    _compName.dispose();
    for (final c in [..._windowStart.values, ..._windowEnd.values]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    final desk = context.read<DeskState>();
    setState(() => loading = true);
    try {
      data = await desk.api.get('/api/league/${widget.slug}/organize');
      final league = Map<String, dynamic>.from(data['league'] as Map);
      _leagueName.text = league['name']?.toString() ?? '';
      _maxTeams.text = '${league['max_teams'] ?? 16}';
      _weeks.text = '${league['weeks'] ?? 6}';
      _startOn.text = league['start_on']?.toString() ?? '';
      status = league['status']?.toString() ?? 'open';
      for (final w in mapList(data['windows'])) {
        final id = mapInt(w, 'id');
        _windowStart.putIfAbsent(id, () => TextEditingController(text: w['starts_at']?.toString() ?? ''));
        _windowEnd.putIfAbsent(id, () => TextEditingController(text: w['ends_at']?.toString() ?? ''));
      }
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
    final requests = mapList(data['join_requests']);
    final officers = mapList(data['officers']);
    final competitions = mapList(data['competitions']);
    final windows = mapList(data['windows']);
    final calendar = mapList(data['calendar']);
    final isHost = data['is_host'] == true;

    return Scaffold(
      appBar: AppBar(title: Text(league?['name']?.toString() ?? 'Organize')),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  NoticeBanner(error: desk.error, notice: desk.notice),
                  Text(isHost ? 'League host' : 'League officer', style: const TextStyle(color: deskGold)),
                  const SizedBox(height: 16),
                  const Text('Join requests and invitations', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  if (requests.isEmpty) const EmptyText('No pending requests.'),
                  ...requests.map((r) => ListTile(
                        title: Text('${r['manager_name']} · ${r['team_name']}'),
                        subtitle: Text('${r['email']} · ${r['kind']} · ${r['status']}'),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            TextButton(onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/requests/${r['id']}/decide', {'accept': true})), child: const Text('Approve')),
                            TextButton(onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/requests/${r['id']}/decide', {'accept': false})), child: const Text('Reject')),
                          ],
                        ),
                      )),
                  TextField(controller: _inviteEmail, decoration: const InputDecoration(labelText: 'Invite by Google email')),
                  const SizedBox(height: 8),
                  TextField(controller: _inviteClub, decoration: const InputDecoration(labelText: 'Suggested club name')),
                  const SizedBox(height: 8),
                  FilledButton(
                    onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/invite', {
                          'email': _inviteEmail.text.trim(),
                          'team_name': _inviteClub.text.trim(),
                        })),
                    child: const Text('Send invitation'),
                  ),
                  const SizedBox(height: 24),
                  const Text('Officers', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  ...officers.map((o) => ListTile(
                        title: Text(o['name']?.toString() ?? ''),
                        subtitle: Text(o['email']?.toString() ?? ''),
                        trailing: isHost
                            ? TextButton(
                                onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/officers/${o['user_id']}/revoke')),
                                child: const Text('Remove'),
                              )
                            : null,
                      )),
                  if (isHost) ...[
                    TextField(controller: _officerEmail, decoration: const InputDecoration(labelText: 'Grant by Google email')),
                    const SizedBox(height: 8),
                    FilledButton(
                      onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/officers', {'email': _officerEmail.text.trim()})),
                      child: const Text('Grant officer'),
                    ),
                  ],
                  const SizedBox(height: 24),
                  const Text('Competitions', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  ...competitions.map((c) => ListTile(
                        title: Text(c['name']?.toString() ?? ''),
                        subtitle: Text('${c['kind_label'] ?? c['kind']} · ${c['team_count'] ?? 0} clubs · ${c['fixture_count'] ?? 0} matches'),
                      )),
                  DropdownButtonFormField<String>(
                    initialValue: compKind,
                    items: const [
                      DropdownMenuItem(value: 'division', child: Text('League level (max 3)')),
                      DropdownMenuItem(value: 'cup', child: Text('Cup')),
                      DropdownMenuItem(value: 'ucl', child: Text('Champions League')),
                      DropdownMenuItem(value: 'event', child: Text('One-off')),
                    ],
                    onChanged: (v) => setState(() => compKind = v ?? 'division'),
                  ),
                  const SizedBox(height: 8),
                  TextField(controller: _compName, decoration: const InputDecoration(labelText: 'Name (optional)')),
                  const SizedBox(height: 8),
                  FilledButton(
                    onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/competitions', {
                          'kind': compKind,
                          'name': _compName.text.trim(),
                        })),
                    child: const Text('Open competition'),
                  ),
                  if (isHost) ...[
                    const SizedBox(height: 24),
                    const Text('Season setup', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    TextField(controller: _leagueName, decoration: const InputDecoration(labelText: 'League name')),
                    const SizedBox(height: 8),
                    TextField(controller: _maxTeams, decoration: const InputDecoration(labelText: 'Max players'), keyboardType: TextInputType.number),
                    const SizedBox(height: 8),
                    TextField(controller: _weeks, decoration: const InputDecoration(labelText: 'Number of weeks'), keyboardType: TextInputType.number),
                    const SizedBox(height: 8),
                    TextField(controller: _startOn, decoration: const InputDecoration(labelText: 'Season start (YYYY-MM-DD)')),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      initialValue: status,
                      items: const [
                        DropdownMenuItem(value: 'open', child: Text('Open for join requests')),
                        DropdownMenuItem(value: 'active', child: Text('Season active')),
                        DropdownMenuItem(value: 'closed', child: Text('Closed')),
                      ],
                      onChanged: (v) => setState(() => status = v ?? 'open'),
                    ),
                    const SizedBox(height: 8),
                    FilledButton(
                      onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/organize', {
                            'name': _leagueName.text.trim(),
                            'max_teams': int.tryParse(_maxTeams.text) ?? 16,
                            'weeks': int.tryParse(_weeks.text) ?? 6,
                            'start_on': _startOn.text.trim(),
                            'status': status,
                          })),
                      child: const Text('Save and rebuild calendar'),
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton(
                      onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/calendar')),
                      child: const Text('Rebuild calendar again'),
                    ),
                    const SizedBox(height: 24),
                    const Text('Window times', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    ...windows.map((w) {
                      final id = mapInt(w, 'id');
                      _windowStart.putIfAbsent(id, () => TextEditingController(text: w['starts_at']?.toString() ?? ''));
                      _windowEnd.putIfAbsent(id, () => TextEditingController(text: w['ends_at']?.toString() ?? ''));
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(w['title']?.toString() ?? w['kind']?.toString() ?? '', style: const TextStyle(fontWeight: FontWeight.w600)),
                            const SizedBox(height: 4),
                            TextField(controller: _windowStart[id], decoration: const InputDecoration(labelText: 'Starts')),
                            const SizedBox(height: 4),
                            TextField(controller: _windowEnd[id], decoration: const InputDecoration(labelText: 'Ends')),
                          ],
                        ),
                      );
                    }),
                    FilledButton(
                      onPressed: () => _act(() => desk.api.post('/api/league/${widget.slug}/windows', {
                            'windows': windows
                                .map((w) => {
                                      'id': w['id'],
                                      'starts_at': _windowStart[mapInt(w, 'id')]?.text ?? '',
                                      'ends_at': _windowEnd[mapInt(w, 'id')]?.text ?? '',
                                    })
                                .toList(),
                          })),
                      child: const Text('Save window times'),
                    ),
                    const SizedBox(height: 24),
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
                              title: Text(w['activity']?.toString() ?? ''),
                              subtitle: Text('${w['period'] ?? ''} · ${w['when_label'] ?? ''}'),
                            )),
                      ];
                    }),
                  ],
                ],
              ),
            ),
    );
  }
}
