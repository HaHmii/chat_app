import 'dart:convert';
import '../config/app_config.dart';
import 'property_model.dart';

// Pattern: <!--PROPS:[{...},{...}]-->
final _propsPattern = RegExp(r'<!--PROPS:(\[.*?\])-->', dotAll: true);

class MessageModel {
  final String id;
  final String text;
  final String senderId;
  final String senderUsername;
  final DateTime createdAt;
  final bool isBot;
  final bool isMe;
  final List<Property>? properties; // null = không có card

  const MessageModel({
    required this.id,
    required this.text,
    required this.senderId,
    required this.senderUsername,
    required this.createdAt,
    required this.isBot,
    required this.isMe,
    this.properties,
  });

  factory MessageModel.fromJson(Map<String, dynamic> json, String botUsername) {
    final username = json['u']?['username'] ?? '';
    final senderId = json['u']?['_id'] ?? '';

    DateTime parsedTime;
    final ts = json['ts'];
    if (ts is Map && ts['\$date'] != null) {
      parsedTime =
          DateTime.fromMillisecondsSinceEpoch(ts['\$date'], isUtc: true)
              .toLocal();
    } else if (ts is String) {
      parsedTime = DateTime.tryParse(ts)?.toLocal() ?? DateTime.now();
    } else {
      parsedTime = DateTime.now();
    }

    final rawText = json['msg'] as String? ?? '';

    // Tách metadata cards khỏi text hiển thị
    String cleanText = rawText;
    List<Property>? properties;
    final match = _propsPattern.firstMatch(rawText);
    if (match != null) {
      try {
        final jsonList = jsonDecode(match.group(1)!) as List;
        properties =
            jsonList.map((e) => Property.fromJson(e as Map<String, dynamic>)).toList();
      } catch (_) {
        properties = null;
      }
      cleanText = rawText.replaceAll(match[0]!, '').trim();
    }

    return MessageModel(
      id: json['_id'] ?? '',
      text: cleanText,
      senderId: senderId,
      senderUsername: username,
      createdAt: parsedTime,
      isBot: username == botUsername,
      isMe: senderId == AppConfig.userId,
      properties: properties,
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
