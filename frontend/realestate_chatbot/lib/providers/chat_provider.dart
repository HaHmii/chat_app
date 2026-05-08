import 'dart:async';
import 'package:flutter/material.dart';
import '../models/message_model.dart';
import '../services/rocketchat_service.dart';
import '../config/app_config.dart';

class ChatProvider extends ChangeNotifier {
  final RocketChatService _service = RocketChatService();

  List<MessageModel> messages   = [];
  bool isLoading                = false;
  bool isConnected              = false;
  bool isBotTyping              = false;
  String? errorMessage;
  String? _roomId;

  StreamSubscription? _subscription;
  StreamSubscription? _connectionSubscription;

  Future<void> init() async {
    isLoading    = true;
    errorMessage = null;
    notifyListeners();

    try {
      // Lấy roomId từ tên channel
      _roomId = AppConfig.roomId;
      if (_roomId == null) {
        throw Exception('Không tìm thấy phòng chat. Vui lòng đăng nhập lại.');
      }

      // Load tin nhắn cũ
      messages = await _service.getMessages(_roomId!);

      // Lắng nghe trạng thái kết nối WebSocket (kể cả khi reconnect)
      _connectionSubscription?.cancel();
      _connectionSubscription = _service.connectionStatus.listen((connected) {
        isConnected = connected;
        notifyListeners();
      });

      // Kết nối WebSocket nhận tin nhắn mới
      final stream = _service.connectWebSocket(_roomId!);
      _subscription = stream.listen(_onNewMessage);
    } catch (e) {
      errorMessage = 'Lỗi kết nối: $e';
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> sendMessage(String text) async {
    if (text.trim().isEmpty || _roomId == null) return;
    isBotTyping = true;
    notifyListeners();
    try {
      await _service.sendMessage(_roomId!, text.trim());
    } catch (e) {
      errorMessage = 'Gửi tin thất bại: $e';
      isBotTyping = false;
      notifyListeners();
    }
  }

  // Chuyển đổi List<MessageModel> thành List<ChatItem> để hiển thị
  List<ChatItem> get chatItems {
    // Sắp xếp tin nhắn theo thời gian tăng dần
    final sorted = [...messages]
      ..sort((a, b) => a.createdAt.compareTo(b.createdAt));

    final List<ChatItem> items = [];
    DateTime? lastDate;

    for (final msg in sorted) {
      final msgDate = DateUtils.dateOnly(msg.createdAt);
      
      // Thêm DateSeparatorItem nếu ngày thay đổi
      if (lastDate == null || !msgDate.isAtSameMomentAs(lastDate)) {
        items.add(DateSeparatorItem(msgDate));
        lastDate = msgDate;
      }
      
      items.add(MessageItem(msg));
    }

    return items;
  }

  void _onNewMessage(MessageModel msg) {
    if (msg.isBot && isBotTyping) {
      isBotTyping = false;
    }
    if (!messages.any((m) => m.id == msg.id)) {
      messages.insert(0, msg);
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _connectionSubscription?.cancel();
    _service.disconnect();
    super.dispose();
  }
}
