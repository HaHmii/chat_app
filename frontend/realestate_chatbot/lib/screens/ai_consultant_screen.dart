import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:provider/provider.dart';
import '../providers/chat_provider.dart';
import '../models/message_model.dart';
import '../models/property_model.dart';
import 'package:intl/intl.dart';

class AiConsultantScreen extends StatefulWidget {
  const AiConsultantScreen({super.key});

  @override
  State<AiConsultantScreen> createState() => _AiConsultantScreenState();
}

class _AiConsultantScreenState extends State<AiConsultantScreen> {
  final TextEditingController _ctrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();

  ChatProvider? _chatProvider;
  int _lastMsgCount = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _chatProvider = context.read<ChatProvider>();
      _chatProvider!.init();
      _chatProvider!.addListener(_onProviderChange);
    });
  }

  void _onProviderChange() {
    final count = _chatProvider?.messages.length ?? 0;
    if (count > _lastMsgCount) {
      _lastMsgCount = count;
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          0,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    }
  }

  @override
  void dispose() {
    _chatProvider?.removeListener(_onProviderChange);
    _ctrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
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
              builder: (_, p, _) => Text(
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
                child: (provider.messages.isEmpty && !provider.isBotTyping)
                    ? _buildEmptyState()
                    : ListView.builder(
                        controller: _scrollCtrl,
                        reverse: true, // Tin nhắn mới ở dưới
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                        itemCount: items.length + (provider.isBotTyping ? 1 : 0),
                        itemBuilder: (_, i) {
                          // Hiển thị typing indicator ở vị trí đầu (dưới cùng do reverse)
                          if (provider.isBotTyping && i == 0) {
                            return const _TypingIndicator();
                          }
                          final offset = provider.isBotTyping ? 1 : 0;
                          final item = items[items.length - 1 - (i - offset)];
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
                    // Scroll to bottom immediately when user sends
                    if (_scrollCtrl.hasClients) {
                      _scrollCtrl.animateTo(0,
                          duration: const Duration(milliseconds: 200),
                          curve: Curves.easeOut);
                    }
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
    final isMe = msg.isMe;
    final hasCards =
        !isMe && msg.properties != null && msg.properties!.isNotEmpty;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment:
            isMe ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          // ── Text bubble ──────────────────────────────────────────
          Row(
            mainAxisAlignment:
                isMe ? MainAxisAlignment.end : MainAxisAlignment.start,
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
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
                      if (isMe)
                        Text(
                          msg.text,
                          style: const TextStyle(
                              color: Colors.white, fontSize: 15),
                        )
                      else
                        MarkdownBody(
                          data: msg.text,
                          styleSheet: MarkdownStyleSheet(
                            p: const TextStyle(
                                color: Colors.black87, fontSize: 15),
                            strong: const TextStyle(
                                color: Colors.black87,
                                fontSize: 15,
                                fontWeight: FontWeight.bold),
                            listBullet: const TextStyle(
                                color: Colors.black87, fontSize: 15),
                            h1: const TextStyle(
                                color: Colors.black87,
                                fontSize: 17,
                                fontWeight: FontWeight.bold),
                            h2: const TextStyle(
                                color: Colors.black87,
                                fontSize: 16,
                                fontWeight: FontWeight.bold),
                            blockSpacing: 6,
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
          // ── Property cards (chỉ hiển thị khi có dữ liệu) ─────────
          if (hasCards)
            Padding(
              padding: const EdgeInsets.only(left: 40, top: 8),
              child: _PropertyCardList(properties: msg.properties!),
            ),
        ],
      ),
    );
  }
}

class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator();

  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(right: 8, top: 4),
            child: CircleAvatar(
              radius: 16,
              child: Icon(Icons.smart_toy_outlined, size: 18),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: Colors.grey[200],
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
                bottomLeft: Radius.circular(4),
                bottomRight: Radius.circular(16),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(3, (i) {
                return AnimatedBuilder(
                  animation: _controller,
                  builder: (_, _) {
                    final phase = ((_controller.value - i * 0.33) % 1.0 + 1.0) % 1.0;
                    final dy = -sin(phase * pi) * 5.0;
                    return Transform.translate(
                      offset: Offset(0, dy),
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: Colors.grey[500],
                          shape: BoxShape.circle,
                        ),
                      ),
                    );
                  },
                );
              }),
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
        BoxShadow(color: Colors.black.withValues(alpha: 0.05), blurRadius: 5)
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

// ─────────────────────────────────────────────────────────────────────────────
// Property card widgets
// ─────────────────────────────────────────────────────────────────────────────

class _PropertyCardList extends StatelessWidget {
  final List<Property> properties;
  const _PropertyCardList({required this.properties});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 230,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: properties.length,
        separatorBuilder: (_, _) => const SizedBox(width: 10),
        itemBuilder: (_, i) => _PropertyCard(prop: properties[i]),
      ),
    );
  }
}

class _PropertyCard extends StatelessWidget {
  final Property prop;
  const _PropertyCard({required this.prop});

  @override
  Widget build(BuildContext context) {
    final isRent = prop.type == 'rent';
    final typeColor = isRent ? Colors.green[700]! : Colors.blue[700]!;
    final priceText = prop.priceDisplay ??
        '${prop.price.toStringAsFixed(0)} ${prop.priceUnit ?? 'VNĐ'}';
    final locationText = prop.districtName ?? prop.address;

    return Container(
      width: 190,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 6, offset: Offset(0, 2))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Thumbnail ───────────────────────────────────────────
          ClipRRect(
            borderRadius:
                const BorderRadius.vertical(top: Radius.circular(12)),
            child: prop.thumbnailUrl != null
                ? Image.network(
                    prop.thumbnailUrl!,
                    height: 100,
                    width: double.infinity,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => _placeholder(),
                  )
                : _placeholder(),
          ),
          // ── Info ────────────────────────────────────────────────
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Badges: loại + phân loại
                  Row(
                    children: [
                      _Badge(
                        prop.typeDisplay ?? (isRent ? 'Cho thuê' : 'Bán'),
                        typeColor,
                      ),
                      if (prop.categoryDisplay != null) ...[
                        const SizedBox(width: 4),
                        _Badge(prop.categoryDisplay!, Colors.grey[600]!),
                      ],
                    ],
                  ),
                  const SizedBox(height: 4),
                  // Giá
                  Text(
                    priceText,
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: typeColor,
                      fontSize: 13,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  // Tiêu đề
                  Text(
                    prop.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12, color: Colors.black87),
                  ),
                  const Spacer(),
                  // Diện tích · phòng ngủ · WC
                  Row(
                    children: [
                      const Icon(Icons.straighten, size: 11, color: Colors.grey),
                      const SizedBox(width: 2),
                      Text('${prop.area.toStringAsFixed(0)}m²',
                          style: const TextStyle(fontSize: 11, color: Colors.grey)),
                      if (prop.bedrooms != null) ...[
                        const SizedBox(width: 6),
                        const Icon(Icons.bed_outlined, size: 11, color: Colors.grey),
                        const SizedBox(width: 2),
                        Text('${prop.bedrooms}',
                            style: const TextStyle(fontSize: 11, color: Colors.grey)),
                      ],
                      if (prop.bathrooms != null) ...[
                        const SizedBox(width: 6),
                        const Icon(Icons.bathtub_outlined, size: 11, color: Colors.grey),
                        const SizedBox(width: 2),
                        Text('${prop.bathrooms}',
                            style: const TextStyle(fontSize: 11, color: Colors.grey)),
                      ],
                    ],
                  ),
                  const SizedBox(height: 2),
                  // Quận
                  Row(
                    children: [
                      const Icon(Icons.location_on_outlined,
                          size: 11, color: Colors.grey),
                      const SizedBox(width: 2),
                      Flexible(
                        child: Text(
                          locationText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 11, color: Colors.grey),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _placeholder() => Container(
        height: 100,
        width: double.infinity,
        color: Colors.grey[200],
        child: const Icon(Icons.home_outlined, size: 36, color: Colors.grey),
      );
}

class _Badge extends StatelessWidget {
  final String label;
  final Color color;
  const _Badge(this.label, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: TextStyle(
            fontSize: 10, color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
}
