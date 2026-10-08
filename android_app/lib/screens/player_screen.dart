import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';

class PlayerScreen extends StatefulWidget {
  const PlayerScreen({super.key, required this.slug});
  final String slug;

  @override
  State<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends State<PlayerScreen> {
  Map<String, dynamic> data = {};
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final desk = context.read<DeskState>();
    setState(() => loading = true);
    try {
      data = await desk.api.get('/api/players/${widget.slug}');
    } catch (err) {
      desk.fail(err);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _sign(String pid) async {
    final desk = context.read<DeskState>();
    try {
      final result = await desk.api.post('/api/market/sign', {'pid': pid});
      desk.flash(result['message']?.toString() ?? 'Signed');
      await _load();
    } catch (err) {
      desk.fail(err);
    }
  }

  Future<void> _buyout(String pid) async {
    final desk = context.read<DeskState>();
    try {
      final result = await desk.api.post('/api/market/buyout', {'pid': pid});
      desk.flash(result['message']?.toString() ?? 'Buyout complete');
      await _load();
    } catch (err) {
      desk.fail(err);
    }
  }

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    final player = data['player'] is Map ? Map<String, dynamic>.from(data['player'] as Map) : null;
    if (loading || player == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Player')),
        body: loading ? const Center(child: CircularProgressIndicator()) : const EmptyText('Player not found.'),
      );
    }
    final status = player['market_status'] is Map ? Map<String, dynamic>.from(player['market_status'] as Map) : {};
    final groups = player['ability_groups'] is Map ? Map<String, dynamic>.from(player['ability_groups'] as Map) : {};
    final skills = (player['skills'] as List?)?.map((e) => e.toString()).toList() ?? [];
    final styles = (player['ai_styles'] as List?)?.map((e) => e.toString()).toList() ?? [];
    final code = status['code']?.toString();
    return Scaffold(
      appBar: AppBar(title: Text(player['name']?.toString() ?? 'Player')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          NoticeBanner(error: desk.error, notice: desk.notice),
          Row(
            children: [
              PlayerFace(api: desk.api, imageUrl: player['image_url']?.toString(), pid: player['pid']?.toString(), size: 96),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${player['position']} · ${player['card_type'] ?? ''}', style: const TextStyle(color: deskMuted)),
                    Text('OVR ${player['overall']}  MAX ${player['max_overall']}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                    Text('Lv ${player['level']}/${player['max_level']}'),
                    if (status.isNotEmpty) StatusChip(status['label']?.toString() ?? '', code: code),
                    Text('${player['height'] ?? '—'}cm · ${player['weight'] ?? '—'}kg · ${player['foot'] ?? ''}'),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (desk.myTeam != null && code == 'free' && data['can_sign_free'] == true)
            FilledButton(onPressed: () => _sign(player['pid'].toString()), child: Text('Sign for ${player['market_price']}M')),
          if (desk.myTeam != null && code == 'signed' && status['release_clause'] != null && data['clause_window'] != null)
            FilledButton(onPressed: () => _buyout(player['pid'].toString()), child: Text('Buyout ${status['release_clause']}M')),
          const SizedBox(height: 16),
          if (player['pos_grid'] is List) _PosMap(grid: player['pos_grid'] as List),
          const SizedBox(height: 16),
          ...groups.entries.map((entry) {
            final stats = mapList(entry.value);
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 8, bottom: 4),
                  child: Text(entry.key.toUpperCase(), style: const TextStyle(color: deskGold, fontWeight: FontWeight.w700)),
                ),
                ...stats.where((s) => s['hidden'] != true).map((s) {
                  final value = mapInt(s, 'value');
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(child: Text(s['label']?.toString() ?? s['key'].toString())),
                            Text('$value', style: const TextStyle(fontWeight: FontWeight.w700)),
                          ],
                        ),
                        LinearProgressIndicator(value: (value.clamp(0, 99)) / 99, color: _bar(value), backgroundColor: deskPanel2),
                      ],
                    ),
                  );
                }),
              ],
            );
          }),
          if (skills.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('Skills', style: TextStyle(fontWeight: FontWeight.w700)),
            Wrap(spacing: 8, children: skills.map((s) => Chip(label: Text(s))).toList()),
          ],
          if (styles.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('AI styles', style: TextStyle(fontWeight: FontWeight.w700)),
            Wrap(spacing: 8, children: styles.map((s) => Chip(label: Text(s))).toList()),
          ],
        ],
      ),
    );
  }

  Color _bar(int value) {
    if (value >= 90) return deskGold;
    if (value >= 80) return deskGreen;
    if (value >= 70) return deskBlue;
    if (value >= 60) return deskMuted;
    return deskRed;
  }
}

class _PosMap extends StatelessWidget {
  const _PosMap({required this.grid});
  final List<dynamic> grid;

  Map<String, Map<String, dynamic>> get _byPos {
    final out = <String, Map<String, dynamic>>{};
    for (final row in grid) {
      if (row is! List) continue;
      for (final cell in row) {
        if (cell is Map) {
          final data = Map<String, dynamic>.from(cell);
          final pos = data['pos']?.toString();
          if (pos != null) out[pos] = data;
        }
      }
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final byPos = _byPos;
    Widget band(int flex, Widget child) => Expanded(flex: flex, child: child);
    Widget col(List<Widget> children) => Column(children: children.map((c) => Expanded(child: c)).toList());
    return AspectRatio(
      aspectRatio: 1,
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: const Color(0xFF0A0E16),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: deskLine),
        ),
        child: Column(
          children: [
            band(2, Row(children: [
              band(1, _cell(byPos['LWF'])),
              band(1, col([_cell(byPos['CF']), _cell(byPos['SS'])])),
              band(1, _cell(byPos['RWF'])),
            ])),
            band(3, Row(children: [
              band(1, _cell(byPos['LMF'])),
              band(1, col([_cell(byPos['AMF']), _cell(byPos['CMF']), _cell(byPos['DMF'])])),
              band(1, _cell(byPos['RMF'])),
            ])),
            band(2, Row(children: [
              band(1, _cell(byPos['LB'])),
              band(1, col([_cell(byPos['CB']), _cell(byPos['GK'])])),
              band(1, _cell(byPos['RB'])),
            ])),
          ],
        ),
      ),
    );
  }

  Widget _cell(Map<String, dynamic>? data) {
    if (data == null) return const SizedBox.expand();
    final tone = data['tone']?.toString();
    final bg = switch (tone) {
      'high' => const Color(0xFF3ECF8E),
      'mid' => const Color(0xFF0D3D2C),
      'ok' => const Color(0xFF161A22),
      _ => const Color(0xFF101318),
    };
    return Padding(
      padding: const EdgeInsets.all(2.5),
      child: Container(
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(8),
          border: data['primary'] == true ? Border.all(color: const Color(0xFF8EE0B0)) : null,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(data['pos']?.toString() ?? '', style: const TextStyle(color: Colors.white70, fontSize: 10, fontWeight: FontWeight.w700)),
            Text('${data['rating'] ?? ''}', style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700, height: 1.15)),
          ],
        ),
      ),
    );
  }
}
