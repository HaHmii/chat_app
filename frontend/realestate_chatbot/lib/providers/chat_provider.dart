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
  Timer? _pollTimer;
  Timer? _bgPollTimer;
  int _pollAttempts = 0;
  bool _isPollInProgress = false;
  bool _isBgPollInProgress = false;

  Future<void> init() async {
    isLoading    = true;
    errorMessage = null;
    isBotTyping  = false;
    messages     = [];
    _stopPoll();
    _subscription?.cancel();
    _subscription = null;
    notifyListeners();

    try {
      _roomId = AppConfig.roomId;
      if (_roomId == null) {
        throw Exception('Không tìm thấy phòng chat. Vui lòng đăng nhập lại.');
      }
      if (AppConfig.visitorToken == null) {
        throw Exception('Visitor token chưa được set. Vui lòng đăng nhập lại.');
      }

      _connectionSubscription?.cancel();
      _connectionSubscription = _service.connectionStatus.listen((connected) {
        isConnected = connected;
        notifyListeners();
      });

      final stream = _service.connectWebSocket(_roomId!);
      _subscription = stream.listen(
        _onNewMessage,
        onError: (e) {
          errorMessage = e.toString();
          isConnected  = false;
          isBotTyping  = false;
          _stopPoll();
          _stopBgPoll();
          notifyListeners();
        },
      );
      _startBgPoll();
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
      final msgId = await _service.sendMessage(_roomId!, text.trim());

      // Optimistic update: show user message immediately without waiting for WS event
      final userMsg = MessageModel(
        id: msgId.isNotEmpty ? msgId : 'tmp_${DateTime.now().millisecondsSinceEpoch}',
        text: text.trim(),
        senderId: AppConfig.visitorToken ?? '',
        senderUsername: AppConfig.visitorToken ?? '',
        createdAt: DateTime.now(),
        isBot: false,
        isMe: true,
      );
      if (!messages.any((m) => m.id == userMsg.id)) {
        messages.insert(0, userMsg);
        notifyListeners();
      }

      // Start polling as fallback if WebSocket doesn't deliver bot response
      _startPoll();
    } catch (e) {
      errorMessage = 'Gửi tin thất bại: $e';
      isBotTyping = false;
      notifyListeners();
    }
  }

  // Chuyển đổi List<MessageModel> thành List<ChatItem> để hiển thị
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
    // Reset typing indicator as soon as any non-me message arrives
    if (!msg.isMe && isBotTyping) {
      isBotTyping = false;
      _stopPoll();
    }
    if (!messages.any((m) => m.id == msg.id)) {
      messages.insert(0, msg);
    }
    notifyListeners();
  }

  void _startPoll() {
    _stopPoll();
    _pollAttempts = 0;
    _isPollInProgress = false;
    _pollTimer = Timer.periodic(const Duration(seconds: 4), (_) async {
      if (_isPollInProgress) return;
      _pollAttempts++;
      // Give up after ~40 seconds and clear the typing indicator
      if (_pollAttempts > 10 || !isBotTyping) {
        _stopPoll();
        if (isBotTyping) {
          isBotTyping = false;
          notifyListeners();
        }
        return;
      }
      _isPollInProgress = true;
      try {
        final knownIds = messages.map((m) => m.id).toSet();
        await _service.pollNewMessages(_roomId!, knownIds);
      } finally {
        _isPollInProgress = false;
      }
    });
  }

  void _stopPoll() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  void _startBgPoll() {
    _stopBgPoll();
    _bgPollTimer = Timer.periodic(const Duration(seconds: 10), (_) async {
      if (_roomId == null || _isBgPollInProgress) return;
      _isBgPollInProgress = true;
      try {
        final knownIds = messages.map((m) => m.id).toSet();
        await _service.pollNewMessages(_roomId!, knownIds);
      } finally {
        _isBgPollInProgress = false;
      }
    });
  }

  void _stopBgPoll() {
    _bgPollTimer?.cancel();
    _bgPollTimer = null;
  }

  @override
  void dispose() {
    _stopPoll();
    _stopBgPoll();
    _subscription?.cancel();
    _connectionSubscription?.cancel();
    _service.disconnect();
    super.dispose();
  }
}
