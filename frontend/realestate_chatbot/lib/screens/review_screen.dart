import 'package:flutter/material.dart';
import '../models/property_model.dart';
import '../services/property_service.dart';
import '../config/app_config.dart';

class ReviewScreen extends StatefulWidget {
  const ReviewScreen({super.key});

  @override
  State<ReviewScreen> createState() => ReviewScreenState();
}

class ReviewScreenState extends State<ReviewScreen> {
  final _service = PropertyService();
  late Future<List<Property>> _futurePending;

  @override
  void initState() {
    super.initState();
    _futurePending = _service.getPendingProperties();
  }

  Future<void> reload() async {
    if (!mounted) return;
    setState(() {
      _futurePending = _service.getPendingProperties();
    });
    await _futurePending;
  }

  Future<void> _handleReview(Property prop, String action) async {
    String? reason;
    if (action == 'rejected') {
      reason = await _showRejectDialog();
      if (reason == null) return;
    }

    final result = await _service.reviewProperty(prop.id, action, rejectionReason: reason);
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(result['message']),
      backgroundColor: result['success']
          ? (action == 'approved' ? Colors.green : Colors.orange)
          : Colors.red,
    ));

    if (result['success']) {
       await reload();
    }
  }

  Future<String?> _showRejectDialog() async {
    final ctrl = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Lý do từ chối', style: TextStyle(fontWeight: FontWeight.bold)),
        content: TextField(
          controller: ctrl,
          maxLines: 3,
          autofocus: true,
          decoration: InputDecoration(
            hintText: 'Nhập lý do từ chối tin đăng...',
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Huỷ'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red, foregroundColor: Colors.white),
            onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
            child: const Text('Xác nhận từ chối'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return FutureBuilder<List<Property>>(
      future: _futurePending,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return Center(child: CircularProgressIndicator(color: colorScheme.primary));
        }

        if (snapshot.hasError) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.error_outline, size: 50, color: Colors.red),
                const SizedBox(height: 10),
                Text('${snapshot.error}', textAlign: TextAlign.center),
                const SizedBox(height: 10),
                ElevatedButton(
                  onPressed: () => reload(),
                  child: const Text('Thử lại')
                ),
              ],
            ),
          );
        }

        final props = snapshot.data ?? [];

        if (props.isEmpty) {
          return ListView(
            children: [
              SizedBox(
                height: MediaQuery.of(context).size.height * 0.6,
                child: const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.check_circle_outline, size: 64, color: Colors.green),
                      SizedBox(height: 16),
                      Text('Không có tin nào chờ duyệt',
                          style: TextStyle(fontSize: 16, color: Colors.grey)),
                    ],
                  ),
                ),
              ),
            ],
          );
        }

        return RefreshIndicator(
          onRefresh: reload,
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            itemCount: props.length,
            itemBuilder: (context, i) => _PendingPropertyCard(
              property: props[i],
              onApprove: () => _handleReview(props[i], 'approved'),
              onReject: () => _handleReview(props[i], 'rejected'),
            ),
          ),
        );
      },
    );
  }
}

class _PendingPropertyCard extends StatelessWidget {
  final Property property;
  final VoidCallback onApprove;
  final VoidCallback onReject;

  const _PendingPropertyCard({
    required this.property,
    required this.onApprove,
    required this.onReject,
  });

  String _getImageUrl(String url) {
    if (url.startsWith('http')) return url;
    return '${AppConfig.baseAppUrl}/$url';
  }

  static const Map<String, String> _categoryLabels = {
    'apartment': 'Căn hộ',
    'house': 'Nhà ở',
    'land': 'Đất nền',
    'villa': 'Biệt thự',
    'townhouse': 'Nhà phố',
    'shophouse': 'Shophouse',
    'office': 'Văn phòng',
  };

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final rawPrice = property.price % 1 == 0
        ? property.price.toInt().toString()
        : property.price.toString();
    final priceDisplay = property.priceUnit != null
        ? '$rawPrice ${property.priceUnit}'
        : rawPrice;

    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      clipBehavior: Clip.antiAlias,
      elevation: 3,
      shadowColor: Colors.black.withValues(alpha: 0.1),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 16 / 9,
            child: property.thumbnailUrl != null
                ? Image.network(
                    _getImageUrl(property.thumbnailUrl!),
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => Container(
                        color: Colors.grey[300],
                        child: const Icon(Icons.broken_image, size: 50, color: Colors.grey)),
                  )
                : Container(
                    color: Colors.grey[300],
                    child: const Icon(Icons.home_work, size: 50, color: Colors.grey)),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  property.title,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 6),
                Text(
                  '$priceDisplay  •  ${property.area} m²',
                  style: TextStyle(
                    fontSize: 15,
                    color: colorScheme.primary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Row(children: [
                  _chip(
                    property.type == 'sell' ? 'Bán' : 'Cho thuê',
                    colorScheme.primary,
                  ),
                  const SizedBox(width: 8),
                  _chip(
                    _categoryLabels[property.category] ?? property.category,
                    Colors.blueGrey,
                  ),
                ]),
                const SizedBox(height: 8),
                Row(children: [
                  Icon(Icons.location_on_outlined, size: 14, color: colorScheme.primary),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      property.address,
                      style: const TextStyle(fontSize: 13, color: Colors.black54),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ]),
                if (property.description != null && property.description!.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    property.description!,
                    style: const TextStyle(fontSize: 13, color: Colors.black54),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
                const SizedBox(height: 12),
                const Divider(height: 1),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onReject,
                      icon: const Icon(Icons.close, size: 18),
                      label: const Text('Từ chối', style: TextStyle(fontWeight: FontWeight.bold)),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.red,
                        side: const BorderSide(color: Colors.red),
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: onApprove,
                      icon: const Icon(Icons.check, size: 18),
                      label: const Text('Duyệt', style: TextStyle(fontWeight: FontWeight.bold)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.green[700],
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                  ),
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _chip(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(label,
          style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600)),
    );
  }
}
