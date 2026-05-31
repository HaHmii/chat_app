import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../config/app_config.dart';

class AuthService {
  final _storage = const FlutterSecureStorage();

  Future<Map<String, dynamic>> login(String username, String password) async {
    final url = Uri.parse('${AppConfig.baseAppUrl}/auth/login');

    final response = await http.post(
      url,
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: {'username': username, 'password': password},
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);

      await _storage.write(key: 'jwt_token', value: data['access_token']);

      AppConfig.setRCAuth(
        rid: data['rc_room_id'],
        vtoken: data['rc_visitor_token'],
      );

      // Lưu thông tin người dùng bổ sung
      AppConfig.setUserInfo(
        name: data['full_name'] ?? 'Người dùng',
        uname: username,
        mail: data['email'] ?? '',
        urole: data['role'] ?? 'guest',
      );

      return {'success': true, 'message': 'Đăng nhập thành công'};
    } else {
      final errorData = jsonDecode(response.body);
      return {
        'success': false,
        'message': errorData['detail'] ?? 'Đăng nhập thất bại',
      };
    }
  }

  Future<Map<String, dynamic>> register({
    required String fullName,
    required String username,
    required String email,
    required String phoneNumber,
    required String password,
    required String role,
  }) async {
    final url = Uri.parse('${AppConfig.baseAppUrl}/auth/register');

    final response = await http.post(
      url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'full_name': fullName,
        'username': username,
        'email': email,
        'phone_number': phoneNumber,
        'password': password,
        'role': role,
      }),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);

      // Sau khi đăng ký, backend cũng trả về thông tin RC (nếu có)
      AppConfig.setRCAuth(
        rid: data['rc_room_id'],
        vtoken: data['rc_visitor_token'],
      );

      return {'success': true, 'message': 'Đăng ký thành công'};
    } else {
      final errorData = jsonDecode(response.body);
      return {
        'success': false,
        'message': errorData['detail'] ?? 'Đăng ký thất bại',
      };
    }
  }

  Future<String?> getToken() async {
    return await _storage.read(key: 'jwt_token');
  }

  Future<Map<String, dynamic>> initChatRoom() async {
    final token = await getToken();
    if (token == null) return {'success': false, 'message': 'Chưa đăng nhập'};

    final url = Uri.parse('${AppConfig.baseAppUrl}/auth/init-chat-room');
    final response = await http.post(
      url,
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      AppConfig.setRCAuth(
        rid: data['rc_room_id'],
        vtoken: data['rc_visitor_token'],
      );
      return {'success': true};
    } else {
      final errorData = jsonDecode(response.body);
      return {
        'success': false,
        'message': errorData['detail'] ?? 'Không thể tạo phòng chat',
      };
    }
  }

  Future<void> logout() async {
    await _storage.delete(key: 'jwt_token');
    AppConfig.setRCAuth(rid: null, vtoken: null);
    AppConfig.setUserInfo(name: null, uname: null, mail: null, urole: null);
  }
}
