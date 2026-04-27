import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/appointment_model.dart';

class AppointmentService {
  final _storage = const FlutterSecureStorage();

  Future<String?> _getToken() async {
    return _storage.read(key: 'jwt_token');
  }

  Future<List<Appointment>> getMyAppointments() async {
    final token = await _getToken();
    final response = await http.get(
      Uri.parse('${AppConfig.baseAppUrl}/appointments/my-appointments'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      final List data = jsonDecode(response.body);
      return data
          .map((item) => Appointment.fromJson(item as Map<String, dynamic>))
          .toList();
    }

    throw Exception(_readErrorMessage(response.body));
  }

  Future<List<Appointment>> getOwnerAppointments({int? propertyId}) async {
    final token = await _getToken();
    var url = '${AppConfig.baseAppUrl}/appointments/property-appointments';
    if (propertyId != null) {
      url += '?property_id=$propertyId';
    }

    final response = await http.get(
      Uri.parse(url),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      final List data = jsonDecode(response.body);
      return data
          .map((item) => Appointment.fromJson(item as Map<String, dynamic>))
          .toList();
    }

    throw Exception(_readErrorMessage(response.body));
  }

  Future<Map<String, dynamic>> createAppointment({
    required int propertyId,
    required DateTime proposedTime,
    String? note,
  }) async {
    final token = await _getToken();
    if (token == null || token.isEmpty) {
      return {
        'success': false,
        'message': 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
      };
    }

    try {
      final response = await http.post(
        Uri.parse('${AppConfig.baseAppUrl}/appointments/'),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({
          'property_id': propertyId,
          'proposed_time': proposedTime.toUtc().toIso8601String(),
          'note': note?.trim().isEmpty == true ? null : note?.trim(),
        }),
      );

      if (response.statusCode == 201) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return {
          'success': true,
          'message': data['message'] ?? 'Đặt lịch hẹn thành công',
          'data': data['data'],
        };
      }

      return {
        'success': false,
        'message': _readErrorMessage(response.body),
        'status_code': response.statusCode,
      };
    } catch (e) {
      return {'success': false, 'message': 'Lỗi kết nối: $e'};
    }
  }

  Future<Map<String, dynamic>> confirmAppointment({
    required int appointmentId,
  }) async {
    return _patchAppointment(
      path: '/appointments/$appointmentId/confirm',
      body: const {},
    );
  }

  Future<Map<String, dynamic>> counterAppointment({
    required int appointmentId,
    required DateTime counterProposedTime,
  }) async {
    return _patchAppointment(
      path: '/appointments/$appointmentId/counter',
      body: {
        'counter_proposed_time': counterProposedTime.toUtc().toIso8601String(),
      },
    );
  }

  Future<Map<String, dynamic>> cancelAppointment({
    required int appointmentId,
    required String cancelledBy,
    required String cancelReason,
  }) async {
    return _patchAppointment(
      path: '/appointments/$appointmentId/cancel',
      body: {
        'cancelled_by': cancelledBy,
        'cancel_reason': cancelReason.trim(),
      },
    );
  }

  Future<Map<String, dynamic>> _patchAppointment({
    required String path,
    required Map<String, dynamic> body,
  }) async {
    final token = await _getToken();
    if (token == null || token.isEmpty) {
      return {
        'success': false,
        'message': 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
      };
    }

    try {
      final response = await http.patch(
        Uri.parse('${AppConfig.baseAppUrl}$path'),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode(body),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return {
          'success': true,
          'message': data['message'] ?? 'Thao tác thành công',
          'data': data['data'],
        };
      }

      return {
        'success': false,
        'message': _readErrorMessage(response.body),
        'status_code': response.statusCode,
      };
    } catch (e) {
      return {'success': false, 'message': 'Lỗi kết nối: $e'};
    }
  }

  String _readErrorMessage(String rawBody) {
    try {
      final decoded = jsonDecode(rawBody);
      if (decoded is Map<String, dynamic>) {
        return decoded['detail']?.toString() ??
            decoded['message']?.toString() ??
            'Thao tác thất bại';
      }
      return 'Thao tác thất bại';
    } catch (_) {
      return 'Thao tác thất bại';
    }
  }
}
