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
  StreamController<MessageModel>? _messageController;
  final StreamController<bool> _connectionController =
      StreamController<bool>.broadcast();
  String? _activeRoomId;
  Timer? _pingTimer;
  Timer? _reconnectTimer;
  bool _disposed = false;

  Stream<bool> get connectionStatus => _connectionController.stream;

  Options get _authOptions {
    return Options(headers: {
      'X-Auth-Token': AppConfig.authToken ?? '',
      'X-User-Id': AppConfig.userId ?? '',
      'Content-Type': 'application/json',
    });
  }

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

  Stream<MessageModel> connectWebSocket(String roomId) {
    _disposed = false;
    _activeRoomId = roomId;
    _messageController = StreamController<MessageModel>.broadcast();
    _connectInternal(roomId);
    return _messageController!.stream;
  }

  void _connectInternal(String roomId) {
    if (_disposed) return;

    _pingTimer?.cancel();
    _channel?.sink.close();

    try {
      _channel = WebSocketChannel.connect(Uri.parse(AppConfig.wsUrl));

      _send({'msg': 'connect', 'version': '1', 'support': ['1']});
      _send({
        'msg': 'method',
        'method': 'login',
        'id': 'login-rc',
        'params': [
          {'resume': AppConfig.authToken}
        ],
      });
      _send({
        'msg': 'sub',
        'id': 'sub-$roomId',
        'name': 'stream-room-messages',
        'params': [roomId, false],
      });

      // Gửi ping mỗi 25 giây để giữ kết nối sống
      _pingTimer = Timer.periodic(const Duration(seconds: 25), (_) {
        _send({'msg': 'ping'});
      });

      _channel!.stream.listen(
        (raw) {
          final data = jsonDecode(raw as String);

          if (data['msg'] == 'ping') {
            _send({'msg': 'pong'});
            return;
          }

          // Login thành công → kết nối ổn định
          if (data['msg'] == 'result' && data['id'] == 'login-rc') {
            _connectionController.add(true);
          }

          if (data['msg'] == 'changed' &&
              data['collection'] == 'stream-room-messages') {
            final args = data['fields']?['args'];
            if (args != null && args.isNotEmpty) {
              final msg = MessageModel.fromJson(args[0], AppConfig.botUsername);
              _messageController?.add(msg);
            }
          }
        },
        onError: (e) {
          print('WebSocket error: $e');
          _scheduleReconnect();
        },
        onDone: () {
          print('WebSocket closed — đang kết nối lại...');
          _scheduleReconnect();
        },
      );
    } catch (e) {
      print('WebSocket connection error: $e');
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_disposed || _activeRoomId == null) return;
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    _connectionController.add(false);
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (!_disposed && _activeRoomId != null) {
        print('Reconnecting WebSocket...');
        _connectInternal(_activeRoomId!);
      }
    });
  }

  void _send(Map<String, dynamic> data) {
    _channel?.sink.add(jsonEncode(data));
  }

  void disconnect() {
    _disposed = true;
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _messageController?.close();
    _connectionController.close();
    _activeRoomId = null;
  }
}
