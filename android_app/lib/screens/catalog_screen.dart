import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'player_screen.dart';

class CatalogScreen extends StatefulWidget {
  const CatalogScreen({super.key});

  @override
  State<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends State<CatalogScreen> {
  Map<String, dynamic> data = {};
  bool loading = true;
  final _q = TextEditingController();
  String position = '';
  String cardType = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  Future<void> _load({bool spin = true}) async {
    final desk = context.read<DeskState>();
    if (spin) setState(() => loading = true);
    try {
      data = await desk.api.get('/api/players', query: {
        'q': _q.text.trim(),
        'position': position,
        'card_type': cardType,
      });
    } catch (err) {
      desk.fail(err);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    final players = mapList(data['players']);
    final cardTypes = ((data['card_types'] as List?) ?? ['Standard']).map((e) => e.toString()).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Players')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                NoticeBanner(error: desk.error, notice: desk.notice),
                const Text(
                  'All players. Status shows Available or Signed once you pick a league. Join a club to sign from the market.',
                  style: TextStyle(color: deskMuted, fontSize: 13),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _q,
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: 'Name, club, nationality, pack',
                    suffixIcon: IconButton(icon: const Icon(Icons.search), onPressed: () => _load()),
                  ),
                  onChanged: (_) => _load(spin: false),
                  onSubmitted: (_) => _load(spin: false),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        initialValue: position.isEmpty ? null : position,
                        decoration: const InputDecoration(labelText: 'Pos'),
                        items: [
                          const DropdownMenuItem(value: null, child: Text('All')),
                          ...desk.positions.map((p) => DropdownMenuItem(value: p, child: Text(p))),
                        ],
                        onChanged: (v) {
                          setState(() => position = v ?? '');
                          _load();
                        },
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        initialValue: cardType.isEmpty ? null : cardType,
                        decoration: const InputDecoration(labelText: 'Card'),
                        items: [
                          const DropdownMenuItem(value: null, child: Text('All cards')),
                          const DropdownMenuItem(value: 'Standard', child: Text('Standard only')),
                          ...cardTypes.where((t) => t != 'Standard').map((t) => DropdownMenuItem(value: t, child: Text(t))),
                        ],
                        onChanged: (v) {
                          setState(() => cardType = v ?? '');
                          _load();
                        },
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          Expanded(
            child: loading
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: () => _load(),
                    child: players.isEmpty
                        ? ListView(
                            children: [
                              EmptyText(_q.text.trim().isEmpty ? 'No players in this list.' : 'No players match "${_q.text.trim()}".'),
                            ],
                          )
                        : ListView.builder(
                      itemCount: players.length,
                      itemBuilder: (context, i) {
                        final p = players[i];
                        return PlayerTile(
                          api: desk.api,
                          player: p,
                          onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => PlayerScreen(slug: p['slug']?.toString() ?? p['pid'].toString())),
                          ),
                        );
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
