import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/app_config.dart';
import '../models/property_model.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class PropertyService {
  final _storage = const FlutterSecureStorage();

  // Lấy danh sách (Public)
  Future<List<Property>> getProperties({String? type}) async {
    var urlString = '${AppConfig.baseAppUrl}/properties/';
    if (type != null) urlString += '?type=$type';
    
    final response = await http.get(Uri.parse(urlString));

    if (response.statusCode == 200) {
      List data = jsonDecode(response.body);
      return data.map((item) => Property.fromJson(item)).toList();
    } else {
      throw Exception('Lỗi khi tải danh sách bất động sản');
    }
  }

  Future<List<Property>> getPendingProperties() async {
    final token = await _storage.read(key: 'jwt_token');
    final response = await http.get(
      Uri.parse('${AppConfig.baseAppUrl}/properties/pending'),
      headers: {'Authorization': 'Bearer $token'},
    );
    if (response.statusCode == 200) {
      final List data = jsonDecode(response.body);
      return data.map((item) => Property.fromJson(item)).toList();
    }
    throw Exception('Lỗi khi tải danh sách tin chờ duyệt');
  }

  Future<Map<String, dynamic>> reviewProperty(int id, String action, {String? rejectionReason}) async {
    final token = await _storage.read(key: 'jwt_token');
    final body = <String, dynamic>{'action': action};
    if (rejectionReason != null && rejectionReason.isNotEmpty) {
      body['rejection_reason'] = rejectionReason;
    }
    try {
      final response = await http.patch(
        Uri.parse('${AppConfig.baseAppUrl}/properties/$id/review'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
        body: jsonEncode(body),
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return {'success': true, 'message': data['message']};
      }
      final error = jsonDecode(response.body);
      return {'success': false, 'message': error['detail'] ?? 'Thao tác thất bại'};
    } catch (e) {
      return {'success': false, 'message': 'Lỗi kết nối: $e'};
    }
  }

  Future<List<Map<String, dynamic>>> getDistricts() async {
    final response = await http.get(Uri.parse('${AppConfig.baseAppUrl}/districts'));
    if (response.statusCode == 200) {
      final List data = jsonDecode(response.body);
      return data.cast<Map<String, dynamic>>();
    }
    throw Exception('Lỗi khi tải danh sách quận/huyện');
  }

  // Đăng tin (Chủ nhà)
  Future<Map<String, dynamic>> createProperty(Map<String, dynamic> propData) async {
    final url = Uri.parse('${AppConfig.baseAppUrl}/properties/create');
    final token = await _storage.read(key: 'jwt_token');

    try {
      final response = await http.post(
        url,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode(propData),
      );

      if (response.statusCode == 201) {
        return {'success': true, 'message': 'Đăng tin thành công, vui lòng chờ duyệt.'};
      } else {
        final error = jsonDecode(response.body);
        return {'success': false, 'message': error['detail'] ?? 'Đăng tin thất bại'};
      }
    } catch (e) {
      return {'success': false, 'message': 'Lỗi kết nối: $e'};
    }
  }
}
