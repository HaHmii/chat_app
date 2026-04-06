class MessageModel {
  final String id;
  final String text;
  final String senderId;
  final String senderUsername;
  final DateTime createdAt;
  final bool isBot;

  MessageModel({
    required this.id,
    required this.text,
    required this.senderId,
    required this.senderUsername,
    required this.createdAt,
    required this.isBot,
  });

  factory MessageModel.fromJson(Map<String, dynamic> json, String botUsername) {
    final username = json['u']?['username'] ?? '';

    // Xử lý timestamp — Rocket.chat trả về 2 format khác nhau
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
      senderId       : json['u']?['_id'] ?? '',
      senderUsername : username,
      createdAt      : parsedTime,
      isBot          : username == botUsername,
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