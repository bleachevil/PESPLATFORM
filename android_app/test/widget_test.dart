import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manager_desk/theme.dart';
import 'package:manager_desk/widgets.dart';

void main() {
  test('status colors map market codes', () {
    expect(statusColor('free'), deskGreen);
    expect(statusColor('signed'), deskGold);
  });

  testWidgets('empty text renders', (tester) async {
    await tester.pumpWidget(const Directionality(textDirection: TextDirection.ltr, child: EmptyText('No clubs')));
    expect(find.text('No clubs'), findsOneWidget);
  });
}
