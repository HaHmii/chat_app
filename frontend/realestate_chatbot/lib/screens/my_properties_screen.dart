import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/property_model.dart';
import '../services/property_service.dart';

class MyPropertiesScreen extends StatefulWidget {
  const MyPropertiesScreen({super.key});

  @override
  State<MyPropertiesScreen> createState() => MyPropertiesScreenState();
}

class MyPropertiesScreenState extends State<MyPropertiesScreen> {
  final _service = PropertyService();
  late Future<List<Property>> _futureProperties;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    setState(() { _futureProperties = _service.getMyProperties(); });
  }

  void reload() => _load();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Property>>(
      future: _futureProperties,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline, size: 48, color: Colors.red),
                const SizedBox(height: 12),
                Text(snapshot.error.toString()),
                const SizedBox(height: 12),
                TextButton(onPressed: _load, child: const Text('Thử lại')),
              ],
            ),
          );
        }
        final properties = snapshot.data ?? [];
        if (properties.isEmpty) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.home_work_outlined, size: 64, color: Colors.grey[400]),
                const SizedBox(height: 16),
                Text(
                  'Bạn chưa có tin đăng nào',
                  style: TextStyle(fontSize: 16, color: Colors.grey[600]),
                ),
              ],
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: () async => _load(),
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            itemCount: properties.length,
            itemBuilder: (context, index) => _MyPropertyCard(
              property: properties[index],
              onEdit: () => _openEditDialog(context, properties[index]),
              onDelete: () => _confirmDelete(context, properties[index]),
            ),
          ),
        );
      },
    );
  }

  void _openEditDialog(BuildContext context, Property property) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => _EditPropertyDialog(
        property: property,
        propertyService: _service,
        onSuccess: () {
          _load();
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Cập nhật thành công, tin đang chờ duyệt lại.'),
              backgroundColor: Colors.green,
            ),
          );
        },
      ),
    );
  }

  void _confirmDelete(BuildContext context, Property property) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Xác nhận xóa'),
        content: Text(
          'Bạn có chắc muốn xóa tin "${property.title}"?\nHành động này không thể hoàn tác.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Hủy'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () async {
              Navigator.pop(context);
              final messenger = ScaffoldMessenger.of(context);
              final result = await _service.deleteProperty(property.id);
              if (!mounted) return;
              if (result['success'] == true) {
                _load();
                messenger.showSnackBar(
                  const SnackBar(
                    content: Text('Đã xóa tin đăng.'),
                    backgroundColor: Colors.red,
                  ),
                );
              } else {
                messenger.showSnackBar(
                  SnackBar(content: Text(result['message'] ?? 'Xóa thất bại')),
                );
              }
            },
            child: const Text('Xóa'),
          ),
        ],
      ),
    );
  }
}

class _MyPropertyCard extends StatelessWidget {
  final Property property;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _MyPropertyCard({
    required this.property,
    required this.onEdit,
    required this.onDelete,
  });

  String _getImageUrl(String url) {
    if (url.startsWith('http')) return url;
    return '${AppConfig.baseAppUrl}/$url';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = property.status ?? 'pending';

    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      clipBehavior: Clip.antiAlias,
      elevation: 2,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Stack(
            children: [
              AspectRatio(
                aspectRatio: 16 / 7,
                child: property.thumbnailUrl != null
                    ? Image.network(
                        _getImageUrl(property.thumbnailUrl!),
                        fit: BoxFit.cover,
                        errorBuilder: (_, _, _) => _placeholder(),
                      )
                    : _placeholder(),
              ),
              Positioned(
                top: 10,
                left: 10,
                child: _StatusBadge(status: status),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  property.title,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  '${property.price % 1 == 0 ? property.price.toInt() : property.price}'
                  '${property.priceUnit != null ? ' ${property.priceUnit}' : ''}'
                  '  •  ${property.area} m²',
                  style: TextStyle(
                    color: colorScheme.primary,
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Icon(Icons.location_on_outlined, size: 14, color: Colors.grey[500]),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        property.address,
                        style: TextStyle(color: Colors.grey[600], fontSize: 13),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
                if (status == 'rejected' &&
                    property.rejectionReason != null &&
                    property.rejectionReason!.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.red[50],
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.red[200]!),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.info_outline, size: 14, color: Colors.red),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            property.rejectionReason!,
                            style: const TextStyle(color: Colors.red, fontSize: 12.5),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
            child: Row(
              children: [
                Expanded(
                  child: TextButton.icon(
                    onPressed: onEdit,
                    icon: const Icon(Icons.edit_outlined, size: 18),
                    label: const Text('Chỉnh sửa'),
                    style: TextButton.styleFrom(
                      foregroundColor: colorScheme.primary,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextButton.icon(
                    onPressed: onDelete,
                    icon: const Icon(Icons.delete_outline, size: 18),
                    label: const Text('Xóa tin'),
                    style: TextButton.styleFrom(foregroundColor: Colors.red),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _placeholder() => Container(
        color: Colors.grey[200],
        child: const Center(
          child: Icon(Icons.home_work, size: 48, color: Colors.grey),
        ),
      );
}

class _StatusBadge extends StatelessWidget {
  final String status;

  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status) {
      'approved' => ('Đã duyệt', Colors.green[700]!),
      'rejected' => ('Từ chối', Colors.red[700]!),
      _ => ('Chờ duyệt', Colors.orange[700]!),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 11,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}

// ─── Edit Dialog ─────────────────────────────────────────────────────────────

class _EditPropertyDialog extends StatefulWidget {
  final Property property;
  final PropertyService propertyService;
  final VoidCallback onSuccess;

  const _EditPropertyDialog({
    required this.property,
    required this.propertyService,
    required this.onSuccess,
  });

  @override
  State<_EditPropertyDialog> createState() => _EditPropertyDialogState();
}

class _EditPropertyDialogState extends State<_EditPropertyDialog> {
  late final TextEditingController _titleCtrl;
  late final TextEditingController _descCtrl;
  late final TextEditingController _addressCtrl;
  late final TextEditingController _wardCtrl;
  late final TextEditingController _streetCtrl;
  late final TextEditingController _priceCtrl;
  late final TextEditingController _areaCtrl;
  late final TextEditingController _bedsCtrl;
  late final TextEditingController _bathsCtrl;
  late final TextEditingController _priceUnitCtrl;

  late String _selectedType;
  late String _selectedCategory;
  String? _selectedDirection;
  int? _selectedDistrictId;
  bool _isLoading = false;
  bool _isLoadingDistricts = true;
  String? _errorMessage;
  List<Map<String, dynamic>> _districts = [];

  static const Map<String, String> _typeLabels = {'sell': 'Bán', 'rent': 'Cho thuê'};
  static const Map<String, String> _categoryLabels = {
    'apartment': 'Căn hộ chung cư',
    'house': 'Nhà ở',
    'land': 'Đất nền',
    'villa': 'Biệt thự',
    'townhouse': 'Nhà phố',
    'shophouse': 'Shophouse',
    'office': 'Văn phòng',
  };
  static const List<String> _directions = [
    'Đông', 'Tây', 'Nam', 'Bắc', 'Đông Bắc', 'Đông Nam', 'Tây Bắc', 'Tây Nam',
  ];

  @override
  void initState() {
    super.initState();
    final p = widget.property;
    _titleCtrl = TextEditingController(text: p.title);
    _descCtrl = TextEditingController(text: p.description ?? '');
    _addressCtrl = TextEditingController(text: p.address);
    _wardCtrl = TextEditingController(text: p.ward ?? '');
    _streetCtrl = TextEditingController(text: p.street ?? '');
    _priceCtrl = TextEditingController(
      text: p.price % 1 == 0 ? p.price.toInt().toString() : p.price.toString(),
    );
    _areaCtrl = TextEditingController(
      text: p.area % 1 == 0 ? p.area.toInt().toString() : p.area.toString(),
    );
    _bedsCtrl = TextEditingController(text: p.bedrooms?.toString() ?? '');
    _bathsCtrl = TextEditingController(text: p.bathrooms?.toString() ?? '');
    _priceUnitCtrl = TextEditingController(text: p.priceUnit ?? '');
    _selectedType = p.type;
    _selectedCategory = p.category;
    _selectedDirection = p.direction;
    _selectedDistrictId = p.districtId;
    _loadDistricts();
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    _addressCtrl.dispose();
    _wardCtrl.dispose();
    _streetCtrl.dispose();
    _priceCtrl.dispose();
    _areaCtrl.dispose();
    _bedsCtrl.dispose();
    _bathsCtrl.dispose();
    _priceUnitCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadDistricts() async {
    try {
      final data = await widget.propertyService.getDistricts();
      if (mounted) setState(() { _districts = data; _isLoadingDistricts = false; });
    } catch (_) {
      if (mounted) setState(() => _isLoadingDistricts = false);
    }
  }

  Future<void> _submit() async {
    setState(() { _errorMessage = null; _isLoading = true; });

    if (_titleCtrl.text.trim().length < 10) {
      setState(() { _errorMessage = 'Tiêu đề phải từ 10 ký tự trở lên'; _isLoading = false; });
      return;
    }
    if (_addressCtrl.text.trim().isEmpty) {
      setState(() { _errorMessage = 'Vui lòng nhập địa chỉ'; _isLoading = false; });
      return;
    }
    if (_selectedDistrictId == null) {
      setState(() { _errorMessage = 'Vui lòng chọn quận/huyện'; _isLoading = false; });
      return;
    }
    final price = double.tryParse(_priceCtrl.text) ?? 0;
    if (price <= 0) {
      setState(() { _errorMessage = 'Vui lòng nhập giá hợp lệ'; _isLoading = false; });
      return;
    }
    final area = double.tryParse(_areaCtrl.text) ?? 0;
    if (area <= 0) {
      setState(() { _errorMessage = 'Vui lòng nhập diện tích hợp lệ'; _isLoading = false; });
      return;
    }

    final result = await widget.propertyService.updateProperty(widget.property.id, {
      'title': _titleCtrl.text.trim(),
      'description': _descCtrl.text.trim(),
      'type': _selectedType,
      'category': _selectedCategory,
      'address': _addressCtrl.text.trim(),
      'district_id': _selectedDistrictId,
      'ward': _wardCtrl.text.trim(),
      'street': _streetCtrl.text.trim(),
      'price': price,
      'area': area,
      'price_unit': _priceUnitCtrl.text.trim().isEmpty ? null : _priceUnitCtrl.text.trim(),
      'bedrooms': int.tryParse(_bedsCtrl.text),
      'bathrooms': int.tryParse(_bathsCtrl.text),
      'direction': _selectedDirection,
    });

    if (!mounted) return;
    if (result['success'] == true) {
      Navigator.pop(context);
      widget.onSuccess();
    } else {
      setState(() { _errorMessage = result['message']; _isLoading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 28),
      clipBehavior: Clip.hardEdge,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.88),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(16, 16, 8, 14),
              color: colorScheme.primary,
              child: Row(
                children: [
                  const Icon(Icons.edit, color: Colors.white),
                  const SizedBox(width: 10),
                  const Expanded(
                    child: Text(
                      'Chỉnh sửa tin đăng',
                      style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: Colors.white),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white),
                    onPressed: () => Navigator.pop(context),
                    visualDensity: VisualDensity.compact,
                  ),
                ],
              ),
            ),
            if (_errorMessage != null)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                color: Colors.red[50],
                child: Row(
                  children: [
                    const Icon(Icons.error_outline, color: Colors.red, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(_errorMessage!, style: const TextStyle(color: Colors.red, fontSize: 13)),
                    ),
                    GestureDetector(
                      onTap: () => setState(() => _errorMessage = null),
                      child: const Icon(Icons.close, color: Colors.red, size: 18),
                    ),
                  ],
                ),
              ),
            Flexible(
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(18, 14, 18, MediaQuery.of(context).viewInsets.bottom + 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _sectionTitle('Thông tin cơ bản'),
                    _field(_titleCtrl, 'Tiêu đề (tối thiểu 10 ký tự)', Icons.title),
                    _field(_descCtrl, 'Mô tả chi tiết', Icons.description, maxLines: 3),
                    Row(
                      children: [
                        Expanded(
                          child: _dropdown('Loại tin', _selectedType, _typeLabels.keys.toList(),
                              labelBuilder: (v) => _typeLabels[v]!,
                              onChanged: (v) => setState(() => _selectedType = v!)),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _dropdown('Loại BĐS', _selectedCategory, _categoryLabels.keys.toList(),
                              labelBuilder: (v) => _categoryLabels[v]!,
                              onChanged: (v) => setState(() => _selectedCategory = v!)),
                        ),
                      ],
                    ),
                    _sectionTitle('Vị trí'),
                    _field(_addressCtrl, 'Địa chỉ', Icons.location_on),
                    Padding(
                      padding: const EdgeInsets.only(bottom: 14),
                      child: _isLoadingDistricts
                          ? const LinearProgressIndicator()
                          : DropdownButtonFormField<int>(
                              initialValue: _selectedDistrictId,
                              decoration: InputDecoration(
                                prefixIcon: const Icon(Icons.location_city, size: 20),
                                filled: true,
                                fillColor: Colors.grey[50],
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  borderSide: BorderSide.none,
                                ),
                              ),
                              hint: const Text('Chọn quận/huyện'),
                              items: _districts
                                  .map((d) => DropdownMenuItem<int>(
                                        value: d['id'] as int,
                                        child: Text(d['name'] as String),
                                      ))
                                  .toList(),
                              isExpanded: true,
                              onChanged: (v) => setState(() => _selectedDistrictId = v),
                            ),
                    ),
                    Row(
                      children: [
                        Expanded(child: _field(_streetCtrl, 'Tên đường', Icons.add_road)),
                        const SizedBox(width: 12),
                        Expanded(child: _field(_wardCtrl, 'Phường/Xã', Icons.map)),
                      ],
                    ),
                    _sectionTitle('Giá & Diện tích'),
                    Row(
                      children: [
                        Expanded(child: _field(_priceCtrl, 'Giá *', Icons.payments, isNumber: true)),
                        const SizedBox(width: 12),
                        Expanded(child: _field(_areaCtrl, 'Diện tích (m²) *', Icons.square_foot, isNumber: true)),
                      ],
                    ),
                    _field(_priceUnitCtrl, 'Đơn giá (VD: Tỷ, Triệu/m², Triệu/tháng)', Icons.label_outline),
                    _sectionTitle('Thông tin chi tiết'),
                    Row(
                      children: [
                        Expanded(child: _field(_bedsCtrl, 'Phòng ngủ', Icons.bed, isNumber: true)),
                        const SizedBox(width: 12),
                        Expanded(child: _field(_bathsCtrl, 'Phòng tắm', Icons.bathtub, isNumber: true)),
                      ],
                    ),
                    _dropdown('Hướng nhà', _selectedDirection, _directions,
                        onChanged: (v) => setState(() => _selectedDirection = v), isOptional: true),
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.amber[50],
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: Colors.amber[300]!),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.info_outline, color: Colors.amber, size: 18),
                          const SizedBox(width: 8),
                          const Expanded(
                            child: Text(
                              'Sau khi chỉnh sửa, tin sẽ cần duyệt lại trước khi hiển thị.',
                              style: TextStyle(fontSize: 12.5, color: Colors.black87),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: colorScheme.primary,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 15),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        onPressed: _isLoading ? null : _submit,
                        child: _isLoading
                            ? const SizedBox(
                                height: 24,
                                width: 24,
                                child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                              )
                            : const Text(
                                'LƯU THAY ĐỔI',
                                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                              ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(String title) => Padding(
        padding: const EdgeInsets.only(bottom: 10, top: 6),
        child: Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.blueGrey)),
      );

  Widget _field(TextEditingController ctrl, String hint, IconData icon,
      {bool isNumber = false, int maxLines = 1}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextField(
        controller: ctrl,
        maxLines: maxLines,
        keyboardType: isNumber ? TextInputType.number : TextInputType.text,
        decoration: InputDecoration(
          hintText: hint,
          prefixIcon: Icon(icon, size: 20),
          filled: true,
          fillColor: Colors.grey[50],
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        ),
      ),
    );
  }

  Widget _dropdown(String label, String? value, List<String> items,
      {required Function(String?) onChanged, String Function(String)? labelBuilder, bool isOptional = false}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: DropdownButtonFormField<String>(
        initialValue: value,
        decoration: InputDecoration(
          labelText: label,
          filled: true,
          fillColor: Colors.grey[50],
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
        ),
        items: [
          if (isOptional)
            const DropdownMenuItem<String>(value: null, child: Text('Không xác định')),
          ...items.map((e) => DropdownMenuItem<String>(
                value: e,
                child: Text(labelBuilder != null ? labelBuilder(e) : e),
              )),
        ],
        isExpanded: true,
        onChanged: onChanged,
      ),
    );
  }
}
