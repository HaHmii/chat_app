import 'package:flutter_dotenv/flutter_dotenv.dart';

class AppConfig {
  static String get baseAppUrl => dotenv.env['APP_BASE_URL'] ?? '';
  static String get baseRCUrl => dotenv.env['RC_BASE_URL'] ?? '';
  static String get wsUrl => dotenv.env['RC_WS_URL'] ?? '';
  static String get botUsername => dotenv.env['RC_BOT_USERNAME'] ?? 'bot.ai';

  // Dynamic values stored after login
  static String? userId;
  static String? authToken;
  static String? roomId;
  // Livechat visitor token (= username) — dùng để auth DDP và gửi tin Livechat
  static String? visitorToken;

  // User Info
  static String? fullName;
  static String? username;
  static String? email;
  static String? role; // 'admin', 'staff', 'owner', 'guest'

  static void setRCAuth({
    required String? uid,
    required String? token,
    required String? rid,
    String? vtoken,
  }) {
    userId = uid;
    authToken = token;
    roomId = rid;
    visitorToken = vtoken;
  }

  static void setUserInfo({required String? name, required String? uname, required String? mail, required String? urole}) {
    fullName = name;
    username = uname;
    email = mail;
    role = urole;
  }
}
