import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state.dart';
import 'catalog_screen.dart';
import 'home_screen.dart';
import 'leagues_screen.dart';
import 'market_screen.dart';
import 'squad_screen.dart';

class ShellScreen extends StatefulWidget {
  const ShellScreen({super.key});

  @override
  State<ShellScreen> createState() => _ShellScreenState();
}

class _ShellScreenState extends State<ShellScreen> {
  int index = 0;

  @override
  Widget build(BuildContext context) {
    final desk = context.watch<DeskState>();
    final joined = desk.myTeam != null;
    final pages = [
      const HomeScreen(),
      const LeaguesScreen(),
      if (joined) const MarketScreen(),
      if (joined) const SquadScreen(),
      const CatalogScreen(),
    ];
    final destinations = [
      const NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
      const NavigationDestination(icon: Icon(Icons.emoji_events_outlined), selectedIcon: Icon(Icons.emoji_events), label: 'Leagues'),
      if (joined) const NavigationDestination(icon: Icon(Icons.storefront_outlined), selectedIcon: Icon(Icons.storefront), label: 'Market'),
      if (joined) const NavigationDestination(icon: Icon(Icons.groups), label: 'Squad'),
      const NavigationDestination(icon: Icon(Icons.search), label: 'Players'),
    ];
    if (desk.shellTab != null && desk.shellTab != index) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final target = desk.shellTab!;
        desk.clearShellTab();
        if (target >= 0 && target < pages.length) {
          setState(() => index = target);
        }
      });
    }
    final safeIndex = index.clamp(0, pages.length - 1);
    if (safeIndex != index) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => index = safeIndex);
      });
    }
    return Scaffold(
      body: pages[safeIndex],
      bottomNavigationBar: NavigationBar(
        selectedIndex: safeIndex,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: destinations,
      ),
    );
  }
}
