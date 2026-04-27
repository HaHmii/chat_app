import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../config/app_config.dart';
import '../models/property_model.dart';
import '../services/appointment_service.dart';
import '../services/property_service.dart';

class PropertyDetailScreen extends StatefulWidget {
  final Property property;
  final List<Property>? properties;
  final int initialIndex;

  const PropertyDetailScreen({
    super.key,
    required this.property,
    this.properties,
    this.initialIndex = 0,
  });

  @override
  State<PropertyDetailScreen> createState() => _PropertyDetailScreenState();
}

class _PropertyDetailScreenState extends State<PropertyDetailScreen> {
  final _service = PropertyService();
  final _pageController = PageController();

  late Future<Property> _futureDetail;
  late Property _currentProperty;
  late int _currentPropertyIndex;
  int _currentImageIndex = 0;

  bool get _canBookAppointment => AppConfig.role == 'guest';
  bool get _hasPropertyPager =>
      widget.properties != null && widget.properties!.length > 1;

  @override
  void initState() {
    super.initState();
    _currentPropertyIndex = _resolveInitialIndex();
    _currentProperty = _resolveInitialProperty();
    _futureDetail = _service.getPropertyDetail(_currentProperty.id);
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  int _resolveInitialIndex() {
    final properties = widget.properties;
    if (properties == null || properties.isEmpty) return 0;

    final matchedIndex = properties.indexWhere(
      (item) => item.id == widget.property.id,
    );
    if (matchedIndex >= 0) return matchedIndex;
    if (widget.initialIndex >= 0 && widget.initialIndex < properties.length) {
      return widget.initialIndex;
    }
    return 0;
  }

  Property _resolveInitialProperty() {
    final properties = widget.properties;
    if (properties != null &&
        properties.isNotEmpty &&
        _currentPropertyIndex >= 0 &&
        _currentPropertyIndex < properties.length) {
      return properties[_currentPropertyIndex];
    }
    return widget.property;
  }

  void _showSnackBar(String message, {Color? backgroundColor}) {
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(content: Text(message), backgroundColor: backgroundColor),
    );
  }

  void _loadProperty(Property property, int index) {
    setState(() {
      _currentProperty = property;
      _currentPropertyIndex = index;
      _currentImageIndex = 0;
      _futureDetail = _service.getPropertyDetail(property.id);
    });

    if (_pageController.hasClients) {
      _pageController.jumpToPage(0);
    }
  }

  void _handleHorizontalDragEnd(DragEndDetails details) {
    final velocity = details.primaryVelocity ?? 0;
    if (!_hasPropertyPager || velocity.abs() < 250) return;

    if (velocity < 0) {
      _goToAdjacentProperty(1);
    } else {
      _goToAdjacentProperty(-1);
    }
  }

  void _goToAdjacentProperty(int delta) {
    final properties = widget.properties;
    if (properties == null || properties.isEmpty) return;

    final nextIndex = _currentPropertyIndex + delta;
    if (nextIndex < 0 || nextIndex >= properties.length) {
      _showSnackBar(
        delta > 0
            ? 'Bạn đang ở căn hộ cuối danh sách'
            : 'Bạn đang ở căn hộ đầu danh sách',
      );
      return;
    }

    _loadProperty(properties[nextIndex], nextIndex);
  }

  Future<void> _openBookingSheet(Property property) async {
    if (!_canBookAppointment) {
      _showSnackBar('Chỉ tài khoản khách mới được đặt lịch hẹn');
      return;
    }

    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => _AppointmentBookingSheet(property: property),
    );

    if (!mounted || created != true) return;
    _showSnackBar(
      'Đặt lịch thành công. Bạn có thể xem trong mục Lịch hẹn.',
      backgroundColor: Colors.green,
    );
  }

  String _getImageUrl(String url) {
    if (url.startsWith('http')) return url;
    return '${AppConfig.baseAppUrl}/$url';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surfaceContainerHighest,
      body: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onHorizontalDragEnd: _handleHorizontalDragEnd,
        child: FutureBuilder<Property>(
          future: _futureDetail,
          builder: (context, snapshot) {
            final property = snapshot.data ?? _currentProperty;
            final images = property.images?.isNotEmpty == true
                ? property.images!
                : (property.thumbnailUrl != null
                      ? [property.thumbnailUrl!]
                      : <String>[]);

            return CustomScrollView(
              slivers: [
                SliverAppBar(
                  expandedHeight: 300,
                  pinned: true,
                  backgroundColor: colorScheme.primary,
                  iconTheme: const IconThemeData(color: Colors.white),
                  flexibleSpace: FlexibleSpaceBar(
                    background: _buildImageSlider(images),
                  ),
                  actions: [
                    if (_hasPropertyPager)
                      Container(
                        margin: const EdgeInsets.only(right: 14),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black45,
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Center(
                          child: Text(
                            '${_currentPropertyIndex + 1}/${widget.properties!.length}',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
                SliverToBoxAdapter(
                  child:
                      snapshot.connectionState == ConnectionState.waiting &&
                          snapshot.data == null
                      ? const Padding(
                          padding: EdgeInsets.all(40),
                          child: Center(child: CircularProgressIndicator()),
                        )
                      : _buildContent(context, property, colorScheme),
                ),
              ],
            );
          },
        ),
      ),
      bottomNavigationBar: _buildBottomBar(colorScheme),
    );
  }

  Widget _buildImageSlider(List<String> images) {
    if (images.isEmpty) {
      return Container(
        color: Colors.grey[300],
        child: const Center(
          child: Icon(Icons.home_work, size: 80, color: Colors.grey),
        ),
      );
    }

    return Stack(
      children: [
        PageView.builder(
          controller: _pageController,
          itemCount: images.length,
          onPageChanged: (index) => setState(() => _currentImageIndex = index),
          itemBuilder: (context, index) => Image.network(
            _getImageUrl(images[index]),
            fit: BoxFit.cover,
            errorBuilder: (_, _, _) => Container(
              color: Colors.grey[300],
              child: const Icon(
                Icons.broken_image,
                size: 80,
                color: Colors.grey,
              ),
            ),
          ),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                stops: const [0.6, 1.0],
                colors: [
                  Colors.transparent,
                  Colors.black.withValues(alpha: 0.45),
                ],
              ),
            ),
          ),
        ),
        if (_hasPropertyPager)
          Positioned(
            left: 16,
            bottom: 18,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.black45,
                borderRadius: BorderRadius.circular(999),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.swipe, color: Colors.white, size: 16),
                  SizedBox(width: 6),
                  Text(
                    'Vuốt để xem căn khác',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
        if (images.length > 1)
          Positioned(
            bottom: 14,
            left: 0,
            right: 0,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(
                images.length,
                (index) => AnimatedContainer(
                  duration: const Duration(milliseconds: 250),
                  margin: const EdgeInsets.symmetric(horizontal: 3),
                  width: _currentImageIndex == index ? 22 : 7,
                  height: 7,
                  decoration: BoxDecoration(
                    color: _currentImageIndex == index
                        ? Colors.white
                        : Colors.white54,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
            ),
          ),
        if (images.length > 1)
          Positioned(
            top: 12,
            right: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.photo_library_outlined,
                    color: Colors.white,
                    size: 14,
                  ),
                  const SizedBox(width: 5),
                  Text(
                    '${_currentImageIndex + 1}/${images.length}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildContent(
    BuildContext context,
    Property property,
    ColorScheme colorScheme,
  ) {
    final rawPrice = property.price % 1 == 0
        ? property.price.toInt().toString()
        : property.price.toString();
    final priceDisplay = property.priceUnit != null
        ? '$rawPrice ${property.priceUnit}'
        : rawPrice;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          color: Colors.white,
          padding: const EdgeInsets.fromLTRB(16, 18, 16, 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  _badge(
                    property.type == 'sell' ? 'Bán' : 'Cho thuê',
                    property.type == 'sell'
                        ? const Color(0xFF1565C0)
                        : Colors.orange[700]!,
                  ),
                  const SizedBox(width: 8),
                  _badge(_categoryLabel(property.category), Colors.teal[700]!),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                property.title,
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  height: 1.3,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                priceDisplay,
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w900,
                  color: colorScheme.primary,
                ),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 20,
                runSpacing: 8,
                children: [
                  _stat(Icons.square_foot_outlined, '${property.area} m²'),
                  if (property.bedrooms != null)
                    _stat(Icons.bed_outlined, '${property.bedrooms} phòng ngủ'),
                  if (property.bathrooms != null)
                    _stat(
                      Icons.bathtub_outlined,
                      '${property.bathrooms} phòng tắm',
                    ),
                  if (property.direction != null)
                    _stat(Icons.explore_outlined, property.direction!),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        _card(
          title: 'Vị trí',
          icon: Icons.location_on_outlined,
          children: [
            _infoRow(Icons.location_on_outlined, 'Địa chỉ', property.address),
            if (property.street != null && property.street!.isNotEmpty)
              _infoRow(Icons.add_road, 'Đường', property.street!),
            if (property.ward != null && property.ward!.isNotEmpty)
              _infoRow(Icons.map_outlined, 'Phường/Xã', property.ward!),
          ],
        ),
        const SizedBox(height: 8),
        _card(
          title: 'Thông tin chi tiết',
          icon: Icons.info_outline,
          children: [
            if (property.legalStatus != null &&
                property.legalStatus!.isNotEmpty)
              _infoRow(Icons.gavel, 'Pháp lý', property.legalStatus!),
            if (property.direction != null)
              _infoRow(
                Icons.explore_outlined,
                'Hướng nhà',
                property.direction!,
              ),
            if (property.amenities != null && property.amenities!.isNotEmpty)
              _infoRow(
                Icons.star_outline,
                'Tiện ích',
                property.amenities!.join(', '),
              ),
            if ((property.legalStatus == null ||
                    property.legalStatus!.isEmpty) &&
                property.direction == null &&
                (property.amenities == null || property.amenities!.isEmpty))
              const Text(
                'Chưa có thông tin',
                style: TextStyle(color: Colors.black45),
              ),
          ],
        ),
        if (property.description != null &&
            property.description!.isNotEmpty) ...[
          const SizedBox(height: 8),
          _card(
            title: 'Mô tả',
            icon: Icons.description_outlined,
            children: [
              Text(
                property.description!,
                style: const TextStyle(
                  height: 1.65,
                  color: Colors.black87,
                  fontSize: 14.5,
                ),
              ),
            ],
          ),
        ],
        const SizedBox(height: 8),
        Container(
          color: Colors.white,
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _sectionTitle('Thông tin người đăng', Icons.person_outline),
              const SizedBox(height: 12),
              Row(
                children: [
                  CircleAvatar(
                    radius: 26,
                    backgroundColor: colorScheme.primary.withValues(
                      alpha: 0.15,
                    ),
                    child: Icon(
                      Icons.person,
                      color: colorScheme.primary,
                      size: 28,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          property.ownerName ?? 'Chủ nhà',
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        if (property.ownerPhone != null &&
                            property.ownerPhone!.isNotEmpty) ...[
                          const SizedBox(height: 2),
                          Text(
                            property.ownerPhone!,
                            style: TextStyle(
                              color: colorScheme.primary,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              const Divider(height: 1),
              const SizedBox(height: 14),
              if (property.createdAt != null)
                _infoRow(
                  Icons.calendar_today_outlined,
                  'Ngày đăng',
                  _formatDate(property.createdAt!),
                ),
              if (property.expiresAt != null)
                _infoRow(
                  _isExpired(property.expiresAt!)
                      ? Icons.event_busy_outlined
                      : Icons.event_available_outlined,
                  'Hết hạn',
                  _formatDate(property.expiresAt!),
                  valueColor: _isExpired(property.expiresAt!)
                      ? Colors.red[600]
                      : null,
                ),
            ],
          ),
        ),
        const SizedBox(height: 110),
      ],
    );
  }

  Widget _buildBottomBar(ColorScheme colorScheme) {
    return FutureBuilder<Property>(
      future: _futureDetail,
      builder: (context, snapshot) {
        final property = snapshot.data ?? _currentProperty;

        return Container(
          padding: EdgeInsets.fromLTRB(
            16,
            12,
            16,
            MediaQuery.of(context).padding.bottom + 12,
          ),
          decoration: BoxDecoration(
            color: Colors.white,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.08),
                blurRadius: 10,
                offset: const Offset(0, -3),
              ),
            ],
          ),
          child: Row(
            children: [
              if (_hasPropertyPager) ...[
                _navButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: _currentPropertyIndex > 0
                      ? () => _goToAdjacentProperty(-1)
                      : null,
                ),
                const SizedBox(width: 10),
              ],
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () => _openBookingSheet(property),
                  icon: const Icon(Icons.calendar_month_rounded),
                  label: Text(
                    _canBookAppointment
                        ? 'Đặt lịch hẹn'
                        : 'Chỉ khách mới được đặt lịch',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _canBookAppointment
                        ? colorScheme.primary
                        : Colors.blueGrey[300],
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    elevation: 0,
                  ),
                ),
              ),
              if (_hasPropertyPager) ...[
                const SizedBox(width: 10),
                _navButton(
                  icon: Icons.arrow_forward_rounded,
                  onTap:
                      widget.properties != null &&
                          _currentPropertyIndex < widget.properties!.length - 1
                      ? () => _goToAdjacentProperty(1)
                      : null,
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _navButton({required IconData icon, VoidCallback? onTap}) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Ink(
        width: 52,
        height: 52,
        decoration: BoxDecoration(
          color: onTap == null ? Colors.grey[200] : Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: onTap == null ? Colors.grey[300]! : Colors.blueGrey[100]!,
          ),
        ),
        child: Icon(
          icon,
          color: onTap == null ? Colors.grey : Colors.blueGrey[700],
        ),
      ),
    );
  }

  Widget _card({
    required String title,
    required IconData icon,
    required List<Widget> children,
  }) {
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _sectionTitle(title, icon),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }

  Widget _sectionTitle(String title, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 18, color: Colors.blueGrey[700]),
        const SizedBox(width: 8),
        Text(
          title,
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.bold,
            color: Colors.black87,
          ),
        ),
      ],
    );
  }

  Widget _infoRow(
    IconData icon,
    String label,
    String value, {
    Color? valueColor,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 17, color: Colors.grey[500]),
          const SizedBox(width: 10),
          SizedBox(
            width: 88,
            child: Text(
              label,
              style: const TextStyle(color: Colors.black45, fontSize: 13.5),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                fontWeight: FontWeight.w500,
                color: valueColor ?? Colors.black87,
                fontSize: 13.5,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _badge(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontWeight: FontWeight.bold,
          fontSize: 12,
        ),
      ),
    );
  }

  Widget _stat(IconData icon, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 17, color: Colors.grey[700]),
        const SizedBox(width: 5),
        Text(
          label,
          style: const TextStyle(
            fontWeight: FontWeight.w600,
            color: Colors.black87,
            fontSize: 13.5,
          ),
        ),
      ],
    );
  }

  String _formatDate(DateTime date) {
    return DateFormat('dd/MM/yyyy').format(date.toLocal());
  }

  bool _isExpired(DateTime date) => date.isBefore(DateTime.now());

  String _categoryLabel(String category) {
    const labels = {
      'apartment': 'Căn hộ',
      'house': 'Nhà ở',
      'land': 'Đất nền',
      'villa': 'Biệt thự',
      'townhouse': 'Nhà phố',
      'shophouse': 'Shophouse',
      'office': 'Văn phòng',
    };
    return labels[category] ?? category;
  }
}

class _AppointmentBookingSheet extends StatefulWidget {
  final Property property;

  const _AppointmentBookingSheet({required this.property});

  @override
  State<_AppointmentBookingSheet> createState() =>
      _AppointmentBookingSheetState();
}

class _AppointmentBookingSheetState extends State<_AppointmentBookingSheet> {
  final AppointmentService _appointmentService = AppointmentService();
  final TextEditingController _noteController = TextEditingController();
  final TextEditingController _dateTimeController = TextEditingController();
  DateTime? _selectedDateTime;
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now().add(const Duration(hours: 1));
    _selectedDateTime = DateTime(
      now.year,
      now.month,
      now.day,
      now.hour,
      now.minute,
    );
    _syncSelectedDateTimeLabel();
  }

  @override
  void dispose() {
    _noteController.dispose();
    _dateTimeController.dispose();
    super.dispose();
  }

  void _syncSelectedDateTimeLabel() {
    _dateTimeController.text = _selectedDateTime == null
        ? ''
        : DateFormat('HH:mm - dd/MM/yyyy').format(_selectedDateTime!);
  }

  Future<void> _pickDateTime() async {
    final now = DateTime.now();
    final pickedDate = await showDatePicker(
      context: context,
      firstDate: now,
      lastDate: now.add(const Duration(days: 365)),
      initialDate: _selectedDateTime?.isAfter(now) == true
          ? _selectedDateTime!
          : now,
    );
    if (pickedDate == null || !mounted) return;

    final pickedTime = await showTimePicker(
      context: context,
      initialTime: _selectedDateTime != null
          ? TimeOfDay.fromDateTime(_selectedDateTime!)
          : TimeOfDay.fromDateTime(now.add(const Duration(hours: 1))),
    );
    if (pickedTime == null) return;

    final merged = DateTime(
      pickedDate.year,
      pickedDate.month,
      pickedDate.day,
      pickedTime.hour,
      pickedTime.minute,
    );

    if (merged.isBefore(now.add(const Duration(minutes: 30)))) {
      _showMessage('Vui lòng chọn thời gian muộn hơn hiện tại ít nhất 30 phút');
      return;
    }

    setState(() {
      _selectedDateTime = merged;
      _syncSelectedDateTimeLabel();
    });
  }

  Future<void> _submit() async {
    if (_selectedDateTime == null) {
      _showMessage('Vui lòng chọn ngày giờ hẹn');
      return;
    }

    setState(() => _isSubmitting = true);
    final result = await _appointmentService.createAppointment(
      propertyId: widget.property.id,
      proposedTime: _selectedDateTime!,
      note: _noteController.text,
    );

    if (!mounted) return;
    setState(() => _isSubmitting = false);

    if (result['success'] == true) {
      Navigator.pop(context, true);
      return;
    }

    _showMessage(result['message']?.toString() ?? 'Đặt lịch thất bại');
  }

  void _showMessage(String message) {
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;

    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      padding: EdgeInsets.fromLTRB(20, 18, 20, bottomInset + 20),
      child: SafeArea(
        top: false,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Center(
                child: Container(
                  width: 48,
                  height: 5,
                  decoration: BoxDecoration(
                    color: Colors.blueGrey[100],
                    borderRadius: BorderRadius.circular(999),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              const Text(
                'Đặt lịch hẹn',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 6),
              Text(
                widget.property.title,
                style: TextStyle(
                  color: colorScheme.onSurfaceVariant,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 18),
              TextField(
                controller: _dateTimeController,
                readOnly: true,
                onTap: _pickDateTime,
                decoration: InputDecoration(
                  labelText: 'Ngày giờ hẹn',
                  hintText: 'Chọn DateTimePicker',
                  prefixIcon: const Icon(Icons.event_available_rounded),
                  suffixIcon: const Icon(Icons.chevron_right_rounded),
                  filled: true,
                  fillColor: colorScheme.primary.withValues(alpha: 0.06),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(18),
                    borderSide: BorderSide(
                      color: colorScheme.primary.withValues(alpha: 0.18),
                    ),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(18),
                    borderSide: BorderSide(
                      color: colorScheme.primary.withValues(alpha: 0.18),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _noteController,
                maxLines: 4,
                decoration: InputDecoration(
                  labelText: 'Ghi chú cho chủ nhà',
                  hintText:
                      'Ví dụ: Tôi muốn xem nhà vào buổi tối, cần chỗ để xe...',
                  alignLabelWithHint: true,
                  filled: true,
                  fillColor: Colors.grey[50],
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(18),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
              const SizedBox(height: 18),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _isSubmitting ? null : _submit,
                  icon: _isSubmitting
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.check_circle_outline),
                  label: Text(
                    _isSubmitting ? 'Đang gửi yêu cầu...' : 'Xác nhận đặt lịch',
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 15,
                    ),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: colorScheme.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
