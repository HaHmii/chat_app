import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/chat_provider.dart';
import '../models/message_model.dart';
import 'package:intl/intl.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _ctrl      = TextEditingController();
  final ScrollController       _scrollCtrl = ScrollController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<ChatProvider>().init();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tư vấn BĐS Hà Nội'),
        backgroundColor: const Color(0xFF1565C0),
        foregroundColor: Colors.white,
        actions: [
          Consumer<ChatProvider>(
            builder: (_, p, __) => Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Row(
                children: [
                  Icon(
                    Icons.circle,
                    size: 10,
                    color: p.isConnected ? Colors.greenAccent : Colors.grey,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    p.isConnected ? 'Online' : 'Offline',
                    style: const TextStyle(fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
      body: Consumer<ChatProvider>(
        builder: (context, provider, _) {
          // Trạng thái đang load
          if (provider.isLoading) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 12),
                  Text('Đang kết nối Rocket.chat...'),
                ],
              ),
            );
          }

          // Trạng thái lỗi
          if (provider.errorMessage != null) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, color: Colors.red, size: 48),
                  const SizedBox(height: 12),
                  Text(provider.errorMessage!),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: provider.init,
                    child: const Text('Thử lại'),
                  ),
                ],
              ),
            );
          }

          return Column(
            children: [
              // Danh sách tin nhắn
              Expanded(
                child: provider.messages.isEmpty
                    ? const Center(
                        child: Text(
                          'Hãy đặt câu hỏi về BĐS Hà Nội',
                          style: TextStyle(color: Colors.grey),
                        ),
                      )
                    :
                ListView.builder(
                  controller  : _scrollCtrl,
                  reverse     : true,
                  padding     : const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 8),
                  itemCount   : provider.chatItems.length,
                  itemBuilder : (_, i) {
                    // reverse:true nên đọc từ cuối lên
                    final item = provider.chatItems[
                    provider.chatItems.length - 1 - i
                    ];
                    return switch (item) {
                      DateSeparatorItem(:final date) => DateSeparator(date: date),
                      MessageItem(:final message)   => _MessageBubble(msg: message),
                    };
                  },
                ),
              ),

              // Input
              _InputBox(
                controller: _ctrl,
                onSend: () {
                  provider.sendMessage(_ctrl.text);
                  _ctrl.clear();
                },
              ),
            ],
          );
        },
      ),
    );
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }
}

class _MessageBubble extends StatelessWidget {
  final MessageModel msg;
  const _MessageBubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    final isMe = !msg.isBot;
    return Align(
      alignment: isMe ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        margin  : const EdgeInsets.symmetric(vertical: 4),
        padding : const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: isMe ? const Color(0xFF1565C0) : Colors.grey.shade200,
          borderRadius: BorderRadius.only(
            topLeft    : const Radius.circular(16),
            topRight   : const Radius.circular(16),
            bottomLeft : Radius.circular(isMe ? 16 : 4),
            bottomRight: Radius.circular(isMe ? 4  : 16),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (msg.isBot)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  'BĐS Assistant',
                  style: TextStyle(
                    fontSize  : 11,
                    color     : Colors.grey.shade600,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            Text(
              msg.text,
              style: TextStyle(
                color   : isMe ? Colors.white : Colors.black87,
                fontSize: 14,
                height  : 1.4,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '${msg.createdAt.hour}:${msg.createdAt.minute.toString().padLeft(2, '0')}',
              style: TextStyle(
                fontSize: 10,
                color   : isMe
                    ? Colors.white.withOpacity(0.6)
                    : Colors.grey.shade500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InputBox extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSend;
  const _InputBox({required this.controller, required this.onSend});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border(
            top: BorderSide(color: Colors.grey.shade200),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller : controller,
                minLines   : 1,
                maxLines   : 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                decoration : InputDecoration(
                  hintText    : 'Hỏi về nhà đất Hà Nội...',
                  hintStyle   : TextStyle(color: Colors.grey.shade400),
                  border      : OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide  : BorderSide.none,
                  ),
                  filled      : true,
                  fillColor   : Colors.grey.shade100,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 10,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            CircleAvatar(
              backgroundColor: const Color(0xFF1565C0),
              child: IconButton(
                icon    : const Icon(Icons.send, color: Colors.white, size: 18),
                onPressed: onSend,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class DateSeparator extends StatelessWidget {
  final DateTime date;
  const DateSeparator({super.key, required this.date});

  String _label() {
    final today     = DateUtils.dateOnly(DateTime.now());
    final yesterday = today.subtract(const Duration(days: 1));
    if (date == today)     return 'Hôm nay';
    if (date == yesterday) return 'Hôm qua';
    return DateFormat('dd/MM/yyyy').format(date);
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Expanded(child: Divider()),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Text(_label(),
              style: TextStyle(fontSize: 12, color: Colors.grey[600])),
        ),
        const Expanded(child: Divider()),
      ],
    );
  }
}