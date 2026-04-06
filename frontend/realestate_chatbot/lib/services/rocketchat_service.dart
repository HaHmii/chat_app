import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../config/app_config.dart';
import '../models/message_model.dart';

class RocketChatService {
  final Dio _dio = Dio(BaseOptions(
    baseUrl        : AppConfig.baseUrl,
    connectTimeout : const Duration(seconds: 10),
    receiveTimeout : const Duration(seconds: 15),
  ));

  WebSocketChannel? _channel;
  String? _roomId;   // id nội bộ của room, lấy từ API

  // ── Header xác thực ───────────────────────────────────────────────────────
  Options get _authOptions => Options(headers: {
    'X-Auth-Token' : AppConfig.authToken,
    'X-User-Id'    : AppConfig.userId,
    'Content-Type' : 'application/json',
  });

  // ── Lấy roomId từ tên channel ─────────────────────────────────────────────
  Future<String?> getRoomId(String roomName) async {
    final res = await _dio.get(
      '/api/v1/channels.info',
      queryParameters: {'roomName': roomName},
      options: _authOptions,
    );
    _roomId = res.data['channel']['_id'];
    return _roomId;
  }

  // ── Lấy tin nhắn cũ ───────────────────────────────────────────────────────
  Future<List<MessageModel>> getMessages(String roomId, {int count = 50}) async {
    final res = await _dio.get(
      '/api/v1/channels.messages',
      queryParameters: {'roomId': roomId, 'count': count},
      options: _authOptions,
    );

    final List msgs = res.data['messages'] ?? [];
    return msgs
        .map((m) => MessageModel.fromJson(m, AppConfig.botUsername))
        .toList();
  }

  // ── Gửi tin nhắn ──────────────────────────────────────────────────────────
  Future<void> sendMessage(String roomId, String text) async {
    await _dio.post(
      '/api/v1/chat.sendMessage',
      data: {'message': {'rid': roomId, 'msg': text}},
      options: _authOptions,
    );
  }

  // ── Kết nối WebSocket nhận tin nhắn realtime ──────────────────────────────
  StreamController<MessageModel>? _messageController;

  Stream<MessageModel> connectWebSocket(String roomId) {
    _messageController = StreamController<MessageModel>.broadcast();

    _channel = WebSocketChannel.connect(Uri.parse(AppConfig.wsUrl));

    // 1. Handshake kết nối
    _send({'msg': 'connect', 'version': '1', 'support': ['1']});

    // 2. Xác thực
    _send({
      'msg'    : 'method',
      'method' : 'login',
      'id'     : 'login-1',
      'params' : [{'resume': AppConfig.authToken}],
    });

    // 3. Subscribe stream tin nhắn của room
    _send({
      'msg'    : 'sub',
      'id'     : 'sub-room-$roomId',
      'name'   : 'stream-room-messages',
      'params' : [roomId, false],
    });

    // 4. Lắng nghe và parse message mới
    _channel!.stream.listen(
      (raw) {
        final data = jsonDecode(raw as String);

        // Giữ kết nối WebSocket bằng pong
        if (data['msg'] == 'ping') {
          _send({'msg': 'pong'});
          return;
        }

        // Chỉ xử lý stream-room-messages
        if (data['msg'] == 'changed' &&
            data['collection'] == 'stream-room-messages') {
          final args = data['fields']?['args'];
          if (args != null && args.isNotEmpty) {
            final msg = MessageModel.fromJson(args[0], AppConfig.botUsername);
            _messageController?.add(msg);
          }
        }
      },
      onError: (e) => print('WebSocket error: $e'),
      onDone : ()  => print('WebSocket closed'),
    );

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