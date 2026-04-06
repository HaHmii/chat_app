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
  String? errorMessage;
  String? _roomId;

  StreamSubscription? _subscription;

  Future<void> init() async {
    isLoading    = true;
    errorMessage = null;
    notifyListeners();

    try {
      // Lấy roomId từ tên channel
      _roomId = await _service.getRoomId(AppConfig.roomName);
      if (_roomId == null) throw Exception('Không tìm thấy channel');

      // Load tin nhắn cũ
      messages = await _service.getMessages(_roomId!);

      // Kết nối WebSocket nhận tin nhắn mới
      final stream = _service.connectWebSocket(_roomId!);
      _subscription = stream.listen(_onNewMessage);

      isConnected = true;
    } catch (e) {
      errorMessage = 'Lỗi kết nối: $e';
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> sendMessage(String text) async {
    if (text.trim().isEmpty || _roomId == null) return;
    try {
      await _service.sendMessage(_roomId!, text.trim());
    } catch (e) {
      errorMessage = 'Gửi tin thất bại: $e';
      notifyListeners();
    }
  }

  List<ChatItem> get chatItems {
    final sorted = [...messages]
      ..sort((a, b) => a.createdAt.compareTo(b.createdAt));

    final List<ChatItem> items = [];
    DateTime? lastDate;

    for (final msg in sorted) {
      final msgDate = DateUtils.dateOnly(msg.createdAt);
      if (lastDate == null || !msgDate.isAtSameMomentAs(lastDate)) {
        items.add(DateSeparatorItem(msgDate));
        lastDate = msgDate;
      }
      items.add(MessageItem(msg));
    }

    return items;
  }

  void _onNewMessage(MessageModel msg) {
    if (!messages.any((m) => m.id == msg.id)) {
      messages.insert(0, msg);
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _service.disconnect();
    super.dispose();
  }
}