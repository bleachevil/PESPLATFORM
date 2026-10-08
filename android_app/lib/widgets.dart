import 'package:flutter/material.dart';

import 'api.dart';
import 'theme.dart';

class NoticeBanner extends StatelessWidget {
  const NoticeBanner({super.key, this.error, this.notice});
  final String? error;
  final String? notice;

  @override
  Widget build(BuildContext context) {
    if (error != null && error!.isNotEmpty) {
      return _box(error!, deskRed);
    }
    if (notice != null && notice!.isNotEmpty) {
      return _box(notice!, deskGreen);
    }
    return const SizedBox.shrink();
  }

  Widget _box(String text, Color color) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(text),
    );
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip(this.label, {super.key, this.code});
  final String label;
  final String? code;

  @override
  Widget build(BuildContext context) {
    final color = statusColor(code);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
    );
  }
}

class PlayerFace extends StatelessWidget {
  const PlayerFace({super.key, required this.api, this.imageUrl, this.pid, this.size = 40});
  final ApiClient api;
  final String? imageUrl;
  final String? pid;
  final double size;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Image.network(
        api.artUrl(imageUrl ?? pid),
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => Container(
          width: size,
          height: size,
          color: deskPanel2,
          alignment: Alignment.center,
          child: const Icon(Icons.person, size: 18, color: deskMuted),
        ),
      ),
    );
  }
}

class PlayerTile extends StatelessWidget {
  const PlayerTile({
    super.key,
    required this.api,
    required this.player,
    this.trailing,
    this.onTap,
  });

  final ApiClient api;
  final Map<String, dynamic> player;
  final Widget? trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final status = player['market_status'] is Map ? Map<String, dynamic>.from(player['market_status'] as Map) : null;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            PlayerFace(api: api, imageUrl: player['image_url']?.toString(), pid: player['pid']?.toString()),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(player['name']?.toString() ?? '', style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  Text(
                    [player['position'], player['card_type']].where((e) => e != null && e.toString().isNotEmpty).join(' · '),
                    style: const TextStyle(color: deskMuted, fontSize: 12),
                  ),
                ],
              ),
            ),
            SizedBox(
              width: 48,
              child: Text('${player['overall'] ?? ''}', textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
            if (player['market_price'] != null)
              SizedBox(
                width: 56,
                child: Text('${player['market_price']}M', textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
            const SizedBox(width: 8),
            trailing ??
                (status == null
                    ? const SizedBox(width: 72)
                    : StatusChip(status['label']?.toString() ?? '', code: status['code']?.toString())),
          ],
        ),
      ),
    );
  }
}

class EmptyText extends StatelessWidget {
  const EmptyText(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Text(text, style: const TextStyle(color: deskMuted)),
    );
  }
}

String mapStr(Map? map, String key, [String fallback = '']) {
  if (map == null || map[key] == null) return fallback;
  return map[key].toString();
}

int mapInt(Map? map, String key, [int fallback = 0]) {
  final value = map?[key];
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

List<Map<String, dynamic>> mapList(dynamic value) {
  if (value is! List) return [];
  return value.whereType<Map>().map((row) => Map<String, dynamic>.from(row)).toList();
}
