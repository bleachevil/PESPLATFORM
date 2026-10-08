import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'player_screen.dart';

class MarketScreen extends StatefulWidget {
  const MarketScreen({super.key});

  @override
  State<MarketScreen> createState() => _MarketScreenState();
}

class _MarketScreenState extends State<MarketScreen> {
  Map<String, dynamic> data = {};
  bool loading = true;
  final _q = TextEditingController();
  String position = '';
  String status = '';
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
      data = await desk.api.get('/api/market', query: {
        'q': _q.text.trim(),
        'position': position,
        'status': status,
        'card_type': cardType,
      });
    } catch (err) {
      desk.fail(err);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _sign(Map<String, dynamic> player) async {
    final desk = context.read<DeskState>();
    try {
      final result = await desk.api.post('/api/market/sign', {'pid': player['pid']});
      desk.flash(result['message']?.toString() ?? 'Signed');
      await desk.refreshMe();
      await _load();
    } catch (err) {
      desk.fail(err);
    }
  }

  Future<void> _buyout(Map<String, dynamic> player) async {
    final desk = context.read<DeskState>();
    try {
      final result = await desk.api.post('/api/market/buyout', {'pid': player['pid']});
      desk.flash(result['message']?.toString() ?? 'Buyout complete');
      await desk.refreshMe();
      await _load();
    } catch (err) {
      desk.fail(err);
    }
  }

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    final players = mapList(data['players']);
    final canSign = data['can_sign_free'] == true;
    final clauseWindow = data['clause_window'] != null;
    final cardTypes = ((data['card_types'] as List?) ?? ['Standard']).map((e) => e.toString()).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Player market')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                NoticeBanner(error: desk.error, notice: desk.notice),
                if (desk.myTeam == null) const Text('Join a league first. After you are in a club, the market opens so you can sign available players.', style: TextStyle(color: deskMuted)),
                TextField(
                  controller: _q,
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: 'Find a player to sign',
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
                        initialValue: status.isEmpty ? null : status,
                        decoration: const InputDecoration(labelText: 'Status'),
                        items: const [
                          DropdownMenuItem(value: null, child: Text('Any')),
                          DropdownMenuItem(value: 'free', child: Text('Available')),
                          DropdownMenuItem(value: 'sea', child: Text('In the sea')),
                          DropdownMenuItem(value: 'signed', child: Text('Signed')),
                        ],
                        onChanged: (v) {
                          setState(() => status = v ?? '');
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
                    child: ListView.builder(
                      itemCount: players.length,
                      itemBuilder: (context, i) {
                        final p = players[i];
                        final market = p['market_status'] is Map ? Map<String, dynamic>.from(p['market_status'] as Map) : {};
                        final code = market['code']?.toString();
                        Widget? action;
                        if (desk.myTeam != null && code == 'free' && canSign) {
                          action = FilledButton(onPressed: () => _sign(p), child: const Text('Sign'));
                        } else if (desk.myTeam != null && code == 'signed' && market['release_clause'] != null && clauseWindow) {
                          action = OutlinedButton(onPressed: () => _buyout(p), child: Text('Buyout ${market['release_clause']}M'));
                        }
                        return PlayerTile(
                          api: desk.api,
                          player: p,
                          trailing: action,
                          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => PlayerScreen(slug: p['slug']?.toString() ?? p['pid'].toString()))),
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
