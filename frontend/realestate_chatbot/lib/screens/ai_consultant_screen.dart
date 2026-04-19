import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/chat_provider.dart';
import '../models/message_model.dart';
import 'package:intl/intl.dart';

class AiConsultantScreen extends StatefulWidget {
  const AiConsultantScreen({super.key});

  @override
  State<AiConsultantScreen> createState() => _AiConsultantScreenState();
}

class _AiConsultantScreenState extends State<AiConsultantScreen> {
  final TextEditingController _ctrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<ChatProvider>().init();
    });
  }

  void _sendQuickQuery(String text) {
    context.read<ChatProvider>().sendMessage(text);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        elevation: 0,
        backgroundColor: theme.colorScheme.primary,
        foregroundColor: Colors.white,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Trợ lý AI BĐS Hà Nội',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            Consumer<ChatProvider>(
              builder: (_, p, __) => Text(
                p.isConnected ? 'Sẵn sàng tư vấn' : 'Đang kết nối...',
                style: TextStyle(
                    fontSize: 12,
                    color: p.isConnected ? Colors.greenAccent : Colors.white70
                ),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<ChatProvider>().init(),
            tooltip: 'Làm mới hội thoại',
          ),
        ],
      ),
      body: Consumer<ChatProvider>(
        builder: (context, provider, _) {
          if (provider.isLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          if (provider.errorMessage != null) {
            return _buildErrorState(provider);
          }

          final items = provider.chatItems;

          return Column(
            children: [
              Expanded(
                child: provider.messages.isEmpty
                    ? _buildEmptyState()
                    : ListView.builder(
                        controller: _scrollCtrl,
                        reverse: true, // Tin nhắn mới ở dưới
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                        itemCount: items.length,
                        itemBuilder: (_, i) {
                          // Vì reverse: true nên index 0 là item cuối cùng của list items
                          final item = items[items.length - 1 - i];
                          if (item is DateSeparatorItem) {
                            return _DateSeparator(date: item.date);
                          } else if (item is MessageItem) {
                            return _MessageBubble(msg: item.message);
                          }
                          return const SizedBox.shrink();
                        },
                      ),
              ),
              if (provider.messages.length < 5) _buildQuickActions(),
              _InputBox(
                controller: _ctrl,
                onSend: () {
                  if (_ctrl.text.trim().isNotEmpty) {
                    provider.sendMessage(_ctrl.text);
                    _ctrl.clear();
                  }
                },
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildErrorState(ChatProvider p) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(p.errorMessage!),
          ElevatedButton(onPressed: p.init, child: const Text('Thử lại')),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return const Center(child: Text('Hãy bắt đầu cuộc hội thoại'));
  }

  Widget _buildQuickActions() {
    final actions = [
      'Tìm chung cư Cầu Giấy dưới 3 tỷ',
      'Thủ tục sang tên sổ đỏ',
      'Giá đất Đông Anh hiện tại',
    ];
    return Container(
      height: 45,
      margin: const EdgeInsets.only(bottom: 8),
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        children: actions.map((text) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: ActionChip(
            label: Text(text, style: const TextStyle(fontSize: 12)),
            onPressed: () => _sendQuickQuery(text),
          ),
        )).toList(),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final MessageModel msg;
  const _MessageBubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    // isMe: Tin nhắn của tôi (người dùng đang đăng nhập)
    // isBot: Tin nhắn của Bot AI
    final isMe = msg.isMe;
    
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: isMe ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isMe)
            const Padding(
              padding: EdgeInsets.only(right: 8, top: 4),
              child: CircleAvatar(
                radius: 16,
                child: Icon(Icons.smart_toy_outlined, size: 18),
              ),
            ),
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: isMe ? Colors.blue[700] : Colors.grey[200],
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(16),
                  topRight: const Radius.circular(16),
                  bottomLeft: Radius.circular(isMe ? 16 : 4),
                  bottomRight: Radius.circular(isMe ? 4 : 16),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    msg.text,
                    style: TextStyle(
                      color: isMe ? Colors.white : Colors.black87,
                      fontSize: 15,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    DateFormat('HH:mm').format(msg.createdAt),
                    style: TextStyle(
                      fontSize: 10,
                      color: isMe ? Colors.white70 : Colors.grey,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DateSeparator extends StatelessWidget {
  final DateTime date;
  const _DateSeparator({required this.date});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Row(
        children: [
          const Expanded(child: Divider()),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              DateFormat('dd/MM/yyyy').format(date),
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
          const Expanded(child: Divider()),
        ],
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
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(color: Colors.white, boxShadow: [
        BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 5)
      ]),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              decoration: const InputDecoration(
                hintText: 'Nhập nội dung...',
                border: InputBorder.none,
                contentPadding: EdgeInsets.symmetric(horizontal: 16),
              ),
            ),
          ),
          IconButton(onPressed: onSend, icon: const Icon(Icons.send)),
        ],
      ),
    );
  }
}
