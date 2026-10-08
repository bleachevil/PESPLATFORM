import 'package:flutter/material.dart';

const deskBg = Color(0xFF070B14);
const deskPanel = Color(0xFF10182A);
const deskPanel2 = Color(0xFF162038);
const deskLine = Color(0xFF243152);
const deskText = Color(0xFFE8EEFC);
const deskMuted = Color(0xFF93A0BB);
const deskGold = Color(0xFFE7C45A);
const deskGreen = Color(0xFF3ECF8E);
const deskBlue = Color(0xFF5AA8FF);
const deskRed = Color(0xFFFF6B7A);

ThemeData deskTheme() {
  const scheme = ColorScheme.dark(
    surface: deskPanel,
    primary: deskGold,
    onPrimary: Color(0xFF1A1404),
    secondary: deskGreen,
    error: deskRed,
    onSurface: deskText,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: deskBg,
    appBarTheme: const AppBarTheme(
      backgroundColor: Color(0xFF0B1220),
      foregroundColor: deskText,
      elevation: 0,
    ),
    cardTheme: CardThemeData(
      color: deskPanel,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: deskLine),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: deskPanel2,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: deskLine)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: deskLine)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: deskGold,
        foregroundColor: const Color(0xFF1A1404),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      ),
    ),
    navigationBarTheme: const NavigationBarThemeData(
      backgroundColor: Color(0xFF0B1220),
      indicatorColor: deskPanel2,
    ),
  );
}

Color statusColor(String? code) {
  switch (code) {
    case 'free':
      return deskGreen;
    case 'sea':
      return deskBlue;
    case 'signed':
      return deskGold;
    default:
      return deskMuted;
  }
}
