import '../config/app_config.dart';

class MessageModel {
  final String id;
  final String text;
  final String senderId;
  final String senderUsername;
  final DateTime createdAt;
  final bool isBot;
  final bool isMe;

  MessageModel({
    required this.id,
    required this.text,
    required this.senderId,
    required this.senderUsername,
    required this.createdAt,
    required this.isBot,
    required this.isMe,
  });

  factory MessageModel.fromJson(Map<String, dynamic> json, String botUsername) {
    final username = json['u']?['username'] ?? '';
    final senderId = json['u']?['_id'] ?? '';

    // Xử lý timestamp — Rocket.chat trả về nhiều định dạng
    DateTime parsedTime;
    final ts = json['ts'];
    if (ts is Map && ts['\$date'] != null) {
      parsedTime = DateTime.fromMillisecondsSinceEpoch(ts['\$date'], isUtc: true).toLocal();
    } else if (ts is String) {
      parsedTime = DateTime.tryParse(ts)?.toLocal() ?? DateTime.now();
    } else {  
      parsedTime = DateTime.now();
    }

    return MessageModel(
      id             : json['_id'] ?? '',
      text           : json['msg'] ?? '',
      senderId       : senderId,
      senderUsername : username,
      createdAt      : parsedTime,
      isBot          : username == botUsername,
      isMe           : senderId == AppConfig.userId,
    );
  }
}

sealed class ChatItem {}

class MessageItem extends ChatItem {
  final MessageModel message;
  MessageItem(this.message);
}

class DateSeparatorItem extends ChatItem {
  final DateTime date;
  DateSeparatorItem(this.date);
}
