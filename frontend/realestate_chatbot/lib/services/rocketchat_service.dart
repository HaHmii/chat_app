import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../config/app_config.dart';
import '../models/message_model.dart';

class RocketChatService {
  final Dio _dio = Dio(BaseOptions(
    baseUrl: AppConfig.baseRCUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 15),
  ));

  WebSocketChannel? _channel;

  // Header xác thực lấy động từ AppConfig sau khi login
  Options get _authOptions {
    return Options(headers: {
      'X-Auth-Token': AppConfig.authToken ?? '',
      'X-User-Id': AppConfig.userId ?? '',
      'Content-Type': 'application/json',
    });
  }

  // Lấy tin nhắn từ Direct Message (IM)
  Future<List<MessageModel>> getMessages(String roomId, {int count = 50}) async {
    try {
      final res = await _dio.get(
        '/api/v1/im.history',
        queryParameters: {'roomId': roomId, 'count': count},
        options: _authOptions,
      );

      final List msgs = res.data['messages'] ?? [];
      return msgs
          .map((m) => MessageModel.fromJson(m, AppConfig.botUsername))
          .toList();
    } on DioException catch (e) {
      print('RocketChat getMessages error: ${e.response?.data ?? e.message}');
      rethrow;
    }
  }

  // Gửi tin nhắn
  Future<void> sendMessage(String roomId, String text) async {
    try {
      await _dio.post(
        '/api/v1/chat.sendMessage',
        data: {
          'message': {'rid': roomId, 'msg': text}
        },
        options: _authOptions,
      );
    } on DioException catch (e) {
      print('RocketChat sendMessage error: ${e.response?.data ?? e.message}');
      rethrow;
    }
  }

  // Kết nối WebSocket nhận tin nhắn realtime
  StreamController<MessageModel>? _messageController;

  Stream<MessageModel> connectWebSocket(String roomId) {
    _messageController = StreamController<MessageModel>.broadcast();

    try {
      _channel = WebSocketChannel.connect(Uri.parse(AppConfig.wsUrl));

      // 1. Handshake
      _send({'msg': 'connect', 'version': '1', 'support': ['1']});

      // 2. Xác thực bằng token đã có
      _send({
        'msg': 'method',
        'method': 'login',
        'id': 'login-rc',
        'params': [
          {'resume': AppConfig.authToken}
        ],
      });

      // 3. Subscribe stream tin nhắn của room
      _send({
        'msg': 'sub',
        'id': 'sub-$roomId',
        'name': 'stream-room-messages',
        'params': [roomId, false],
      });

      _channel!.stream.listen(
        (raw) {
          final data = jsonDecode(raw as String);

          if (data['msg'] == 'ping') {
            _send({'msg': 'pong'});
            return;
          }

          if (data['msg'] == 'changed' && data['collection'] == 'stream-room-messages') {
            final args = data['fields']?['args'];
            if (args != null && args.isNotEmpty) {
              final msg = MessageModel.fromJson(args[0], AppConfig.botUsername);
              _messageController?.add(msg);
            }
          }
        },
        onError: (e) => print('WebSocket error: $e'),
        onDone: () => print('WebSocket closed'),
      );
    } catch (e) {
      print('WebSocket connection error: $e');
    }

    return _messageController!.stream;
  }

  void _send(Map<String, dynamic> data) {
    _channel?.sink.add(jsonEncode(data));
  }

  void disconnect() {
    _channel?.sink.close();
    _messageController?.close();
  }
}
