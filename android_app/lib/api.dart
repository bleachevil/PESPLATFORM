import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.message, {this.status = 0});
  final String message;
  final int status;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({this.baseUrl = 'http://10.0.2.2:8000', this.token, this.leagueSlug});

  String baseUrl;
  String? token;
  String? leagueSlug;

  Uri _uri(String path, [Map<String, String>? query]) {
    final root = baseUrl.replaceAll(RegExp(r'/$'), '');
    return Uri.parse('$root$path').replace(queryParameters: {
      if (query != null)
        for (final entry in query.entries)
          if (entry.value.isNotEmpty) entry.key: entry.value,
    });
  }

  Map<String, String> get _headers => {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (token != null && token!.isNotEmpty) 'Authorization': 'Bearer $token',
        if (leagueSlug != null && leagueSlug!.isNotEmpty) 'X-League-Slug': leagueSlug!,
      };

  String artUrl(String? pathOrPid) {
    final root = baseUrl.replaceAll(RegExp(r'/$'), '');
    if (pathOrPid == null || pathOrPid.isEmpty) return '$root/art/0';
    if (pathOrPid.startsWith('http')) return pathOrPid;
    if (pathOrPid.startsWith('/')) return '$root$pathOrPid';
    return '$root/art/$pathOrPid';
  }

  Future<Map<String, dynamic>> get(String path, {Map<String, String>? query}) async {
    final response = await http.get(_uri(path, query), headers: _headers);
    return _decode(response);
  }

  Future<Map<String, dynamic>> post(String path, [Map<String, dynamic>? body]) async {
    final response = await http.post(_uri(path), headers: _headers, body: jsonEncode(body ?? {}));
    return _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    Map<String, dynamic> json = {};
    if (response.body.isNotEmpty) {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) {
        json = decoded;
      } else {
        json = {'data': decoded};
      }
    }
    if (response.statusCode >= 400) {
      throw ApiException(_messageFrom(json, response.statusCode), status: response.statusCode);
    }
    return json;
  }

  String _messageFrom(Map<String, dynamic> json, int status) {
    final error = json['error'];
    if (error != null) return error.toString();
    final detail = json['detail'];
    if (detail is String) return detail;
    if (detail is List && detail.isNotEmpty) {
      final first = detail.first;
      if (first is Map && first['msg'] != null) return first['msg'].toString();
      return first.toString();
    }
    return 'Request failed ($status)';
  }
}
