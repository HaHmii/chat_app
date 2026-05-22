import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import '../models/message_model.dart';

// Mã lỗi DDP mà kết nối lại không giải quyết được
const _fatalDdpErrors = {'error-invalid-token', 'error-not-allowed'};

class RocketChatService {
  static const _maxRetries = 3;
  static const _registerTimeout = Duration(seconds: 10);

  late final Dio _dio = Dio(BaseOptions(
    baseUrl: AppConfig.baseRCUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 15),
  ));

  WebSocketChannel? _channel;
  StreamController<MessageModel>? _msgCtrl;
  final StreamController<bool> _connCtrl =
      StreamController<bool>.broadcast();

  bool _disposed = false;
  int _retryCount = 0;
  int _ddpId = 1;
  Timer? _retryTimer;
  final Map<String, Completer<dynamic>> _pending = {};

  Stream<bool> get connectionStatus => _connCtrl.stream;

  // ── Public ─────────────────────────────────────────────────────────────────

  Stream<MessageModel> connectWebSocket(String roomId) {
    _disposed = false;
    _retryCount = 0;
    _msgCtrl = StreamController<MessageModel>.broadcast();
    _doConnect(roomId);
    return _msgCtrl!.stream;
  }

  Future<String> sendMessage(String roomId, String text) async {
    final token = AppConfig.visitorToken;
    if (token == null) throw Exception('visitorToken chưa được set');
    try {
      final r = await _dio.post(
        '/api/v1/livechat/message',
        data: {'token': token, 'rid': roomId, 'msg': text},
      );
      return (r.data['message'] as Map?)?['_id'] as String? ?? '';
    } on DioException catch (e) {
      print('[RC] sendMessage error: ${e.response?.data ?? e.message}');
      rethrow;
    }
  }

  /// Polling fallback: fetch recent messages and emit only ones not in [knownIds].
  Future<void> pollNewMessages(String roomId, Set<String> knownIds) async {
    final token = AppConfig.visitorToken;
    if (token == null || _msgCtrl == null) return;
    try {
      final r = await _dio.get(
        '/api/v1/livechat/messages.history/$roomId',
        queryParameters: {'token': token, 'count': 20},
      );
      final msgs = (r.data['messages'] as List?) ?? [];
      for (final m in msgs.reversed) {
        final raw = m as Map<String, dynamic>;
        if (_shouldSkip(raw)) continue;
        final parsed = _parse(raw);
        if (!knownIds.contains(parsed.id)) {
          _msgCtrl!.add(parsed);
        }
      }
    } on DioException catch (_) {}
  }

  void disconnect() {
    _disposed = true;
    _retryTimer?.cancel();
    _channel?.sink.close();
    _msgCtrl?.close();
    _connCtrl.add(false);
    _pending.clear();
  }

  // ── WebSocket / DDP ────────────────────────────────────────────────────────

  void _doConnect(String roomId) {
    if (_disposed) return;
    final wsUrl = AppConfig.wsUrl;
    if (wsUrl.isEmpty) {
      print('[WS] RC_WS_URL chưa cấu hình');
      return;
    }
    try {
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      _channel!.stream.listen(
        (raw) => _handleRaw(raw as String, roomId),
        onError: (e) {
          print('[WS] lỗi stream: $e');
          _scheduleReconnect(roomId, fatal: false);
        },
        onDone: () => _scheduleReconnect(roomId, fatal: false),
        cancelOnError: true,
      );
      _send({'msg': 'connect', 'version': '1', 'support': ['1']});
    } catch (e) {
      print('[WS] không thể kết nối: $e');
      _scheduleReconnect(roomId, fatal: false);
    }
  }

  void _handleRaw(String raw, String roomId) {
    final Map<String, dynamic> msg;
    try {
      msg = jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return;
    }

    switch (msg['msg']) {
      case 'connected':
        _retryCount = 0; // reset backoff khi DDP handshake thành công
        _connCtrl.add(true);
        _registerGuest(roomId); // fire-and-forget
        break;

      case 'result':
        _resolveResult(msg);
        break;

      case 'changed':
        if (msg['collection'] == 'stream-room-messages') {
          _emitFromChanged(msg);
        }
        break;

      case 'ping':
        _send({'msg': 'pong'});
        break;
    }
  }

  // Chỉ gọi livechat:registerGuest — KHÔNG gọi DDP login (dành cho RC user, không phải visitor)
  Future<void> _registerGuest(String roomId) async {
    final token = AppConfig.visitorToken;
    if (token == null || token.isEmpty) {
      print('[WS] visitorToken null/empty — hủy kết nối');
      _scheduleReconnect(roomId, fatal: true);
      return;
    }

    try {
      await _call('livechat:registerGuest', [
        {
          'token': token,
          'name': AppConfig.fullName ?? '',
          'email': AppConfig.email ?? '',
        }
      ], timeout: _registerTimeout);

      print('[WS] registerGuest thành công → tải lịch sử + subscribe');
      await _loadHistory(roomId);
      _subscribeRoom(roomId);
    } on TimeoutException {
      print('[WS] registerGuest timeout');
      _scheduleReconnect(roomId, fatal: false);
    } catch (e) {
      final errorCode = e is Map ? '${e['error'] ?? ''}' : '';
      print('[WS] registerGuest lỗi (code=$errorCode): $e');
      _scheduleReconnect(roomId, fatal: _fatalDdpErrors.contains(errorCode));
    }
  }

  Future<dynamic> _call(String method, List<dynamic> params, {Duration? timeout}) {
    final id = '${_ddpId++}';
    final c = Completer<dynamic>();
    _pending[id] = c;
    _send({'msg': 'method', 'method': method, 'id': id, 'params': params});
    return timeout != null ? c.future.timeout(timeout) : c.future;
  }

  void _resolveResult(Map<String, dynamic> msg) {
    final id = msg['id'] as String?;
    final c = id != null ? _pending.remove(id) : null;
    if (c == null || c.isCompleted) return;
    if (msg.containsKey('error')) {
      c.completeError(msg['error'] as Object);
    } else {
      c.complete(msg['result']);
    }
  }

  void _subscribeRoom(String roomId) {
    _send({
      'msg': 'sub',
      'id': 'msgs_$roomId',
      'name': 'stream-room-messages',
      'params': [roomId, false],
    });
  }

  void _emitFromChanged(Map<String, dynamic> msg) {
    final args = ((msg['fields'] as Map?)?['args'] as List?) ?? [];
    for (final m in args) {
      if (m is Map<String, dynamic> && !_shouldSkip(m)) {
        _msgCtrl?.add(_parse(m));
      }
    }
  }

  void _send(Map<String, dynamic> msg) {
    try {
      _channel?.sink.add(jsonEncode(msg));
    } catch (_) {}
  }

  void _scheduleReconnect(String roomId, {required bool fatal}) {
    if (_disposed) return;
    _connCtrl.add(false);
    _channel?.sink.close();
    _channel = null;
    _pending.clear();

    if (fatal) {
      print('[WS] lỗi vĩnh viễn — dừng kết nối lại');
      _msgCtrl?.addError(
        Exception('Kết nối thất bại: token không hợp lệ. Vui lòng đăng nhập lại.'),
      );
      return;
    }

    if (_retryCount >= _maxRetries) {
      print('[WS] đã hết $_maxRetries lần thử — dừng');
      _msgCtrl?.addError(
        Exception('Không thể kết nối tới Rocket.Chat sau $_maxRetries lần thử.'),
      );
      return;
    }

    final delaySec = 1 << _retryCount; // 1s → 2s → 4s
    _retryCount++;
    print('[WS] kết nối lại sau ${delaySec}s (lần $_retryCount/$_maxRetries)');
    _retryTimer?.cancel();
    _retryTimer = Timer(Duration(seconds: delaySec), () => _doConnect(roomId));
  }

  // ── History (REST) ─────────────────────────────────────────────────────────

  Future<void> _loadHistory(String roomId) async {
    final token = AppConfig.visitorToken;
    if (token == null) return;
    try {
      final r = await _dio.get(
        '/api/v1/livechat/messages.history/$roomId',
        queryParameters: {'token': token, 'count': 50},
      );
      // Sắp xếp từ cũ → mới
      final sorted = ((r.data['messages'] as List?) ?? []).reversed.toList();

      // Tìm vị trí tin nhắn đầu tiên của người dùng (không phải bot)
      final firstUserIdx = sorted.indexWhere((m) {
        final username = (m as Map<String, dynamic>)['u']?['username'] ?? '';
        return username != AppConfig.botUsername;
      });

      // Không có tin nhắn nào của user → không hiển thị gì
      if (firstUserIdx == -1) return;

      // Chỉ emit từ tin nhắn đầu tiên của user trở đi, bỏ qua system/rỗng
      for (final m in sorted.skip(firstUserIdx)) {
        final raw = m as Map<String, dynamic>;
        if (!_shouldSkip(raw)) _msgCtrl?.add(_parse(raw));
      }
    } on DioException catch (e) {
      print('[RC] loadHistory error: ${e.response?.data ?? e.message}');
    }
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  /// Trả về true nếu nên bỏ qua tin nhắn này (system message hoặc nội dung rỗng).
  bool _shouldSkip(Map<String, dynamic> m) {
    // RC đánh dấu system messages bằng field 't' (uj, livechat-started, ...)
    if (m['t'] != null) return true;
    final text = (m['msg'] as String? ?? '').trim();
    if (text.isEmpty) return true;
    // Ẩn lệnh handback của nhân viên — user không cần thấy
    if (text == '!bot') return true;
    return false;
  }

  MessageModel _parse(Map<String, dynamic> json) =>
      MessageModel.fromJson(json, AppConfig.botUsername);
}
