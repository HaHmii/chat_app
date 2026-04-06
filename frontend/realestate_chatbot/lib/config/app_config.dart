import 'package:flutter_dotenv/flutter_dotenv.dart';

class AppConfig {
  static String get baseUrl => dotenv.env['RC_BASE_URL'] ?? '';
  static String get wsUrl => dotenv.env['RC_WS_URL'] ?? '';
  static String get userId => dotenv.env['RC_USER_ID'] ?? '';
  static String get authToken => dotenv.env['RC_AUTH_TOKEN'] ?? '';
  static String get roomName => dotenv.env['RC_ROOM_NAME'] ?? '';
  static String get botUsername => dotenv.env['RC_BOT_USERNAME'] ?? '';
}