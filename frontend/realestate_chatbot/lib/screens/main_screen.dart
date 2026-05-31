import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/property_model.dart';
import '../services/auth_service.dart';
import '../services/property_service.dart';
import 'ai_consultant_screen.dart';
import 'appointment_screen.dart';
import 'my_properties_screen.dart';
import 'profile_screen.dart';
import 'property_detail_screen.dart';
import 'review_screen.dart';

class _PropertyFilter {
  final int? districtId;
  final String? category;
  final double? minPrice;
  final double? maxPrice;
  final double? minArea;
  final double? maxArea;

  const _PropertyFilter({
    this.districtId,
    this.category,
    this.minPrice,
    this.maxPrice,
    this.minArea,
    this.maxArea,
  });

  int get activeCount {
    int n = 0;
    if (districtId != null) n++;
    if (category != null) n++;
    if (minPrice != null || maxPrice != null) n++;
    if (minArea != null || maxArea != null) n++;
    return n;
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _selectedIndex = 0;
  String _selectedType = 'sell';
  _PropertyFilter _activeFilter = const _PropertyFilter();
  List<Map<String, dynamic>> _districts = [];
  final PropertyService _propertyService = PropertyService();
  final AuthService _authService = AuthService();
  bool _isInitingChat = false;
  late Future<List<Property>> _futureProperties;
  final _reviewKey = GlobalKey<ReviewScreenState>();
  final _myPropertiesKey = GlobalKey<MyPropertiesScreenState>();
  final _appointmentKey = GlobalKey<AppointmentScreenState>();

  bool get isOwner => AppConfig.role == 'owner';
  bool get isAdmin => AppConfig.role == 'admin';

  // Admin:  [Khám phá(0), Duyệt tin(1), Lịch hẹn(2), Cá nhân(3)]
  // Owner:  [Khám phá(0), Tin của tôi(1), Lịch hẹn(2), Cá nhân(3)]
  // Guest:  [Khám phá(0), Lịch hẹn(1), Cá nhân(2)]
  int get _profileIndex => (isAdmin || isOwner) ? 3 : 2;
  int get _reviewIndex => 1;          // admin only
  int get _myPropertiesIndex => 1;    // owner only
  int get _appointmentIndex => (isAdmin || isOwner) ? 2 : 1;

  String get _appBarTitle {
    if (isAdmin && _selectedIndex == _reviewIndex) return 'Duyệt tin';
    if (isOwner && _selectedIndex == _myPropertiesIndex) return 'Tin của tôi';
    if (_selectedIndex == _appointmentIndex) return 'Lịch hẹn của tôi';
    if (isOwner) return 'Quản lý & Tư vấn';
    return 'Bất động sản Hà Nội';
  }

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  void _fetchData() {
    setState(() {
      _futureProperties = _propertyService.getProperties(
        type: _selectedType,
        districtId: _activeFilter.districtId,
        category: _activeFilter.category,
        minPrice: _activeFilter.minPrice,
        maxPrice: _activeFilter.maxPrice,
        minArea: _activeFilter.minArea,
        maxArea: _activeFilter.maxArea,
      );
    });
  }

  Future<void> _refreshData() async {
    _fetchData();
  }

  Future<void> _openChatbot() async {
    setState(() => _isInitingChat = true);
    final result = await _authService.initChatRoom();
    if (!mounted) return;
    setState(() => _isInitingChat = false);
    if (result['success'] == true) {
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const AiConsultantScreen()),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(result['message'] ?? 'Không thể mở chat'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> _showFilterSheet() async {
    if (_districts.isEmpty) {
      try {
        final data = await _propertyService.getDistricts();
        if (!mounted) return;
        setState(() => _districts = data);
      } catch (_) {}
    }
    if (!mounted) return;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _FilterSheet(
        initial: _activeFilter,
        districts: _districts,
        onApply: (filter) {
          setState(() => _activeFilter = filter);
          _fetchData();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surfaceContainerHighest,
      appBar: _selectedIndex == _profileIndex
          ? null
          : AppBar(
              title: Text(
                _appBarTitle,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              centerTitle: false,
              backgroundColor: colorScheme.primary,
              iconTheme: const IconThemeData(color: Colors.white),
              actions: [
                IconButton(
                  icon: const Icon(Icons.search),
                  onPressed: () => _showComingSoon(context, 'Tìm kiếm'),
                ),
                Badge(
                  isLabelVisible: _activeFilter.activeCount > 0,
                  label: Text('${_activeFilter.activeCount}'),
                  child: IconButton(
                    icon: const Icon(Icons.filter_list),
                    onPressed: _showFilterSheet,
                  ),
                ),
              ],
            ),
      body: IndexedStack(
        index: _selectedIndex,
        children: [
          _buildHomeTab(colorScheme),
          if (isAdmin) ReviewScreen(key: _reviewKey),
          if (isOwner) MyPropertiesScreen(key: _myPropertiesKey),
          AppointmentScreen(key: _appointmentKey),
          const ProfileScreen(),
        ],
      ),
      floatingActionButton: _selectedIndex == _profileIndex
          ? null
          : Column(
              mainAxisAlignment: MainAxisAlignment.end,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (isOwner && _selectedIndex == 0) ...[
                  FloatingActionButton.extended(
                    heroTag: 'add_prop',
                    onPressed: () => _showAddPropertyDialog(context),
                    backgroundColor: Colors.green[700],
                    foregroundColor: Colors.white,
                    icon: const Icon(Icons.add_business),
                    label: const Text(
                      'Đăng Tin',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                  const SizedBox(height: 12),
                ],
                FloatingActionButton.extended(
                  heroTag: 'ai_chat',
                  onPressed: _isInitingChat ? null : _openChatbot,
                  backgroundColor: colorScheme.primary,
                  foregroundColor: Colors.white,
                  icon: _isInitingChat
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Icon(Icons.auto_awesome),
                  label: const Text(
                    'AI Tư Vấn',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (int index) {
          if (isAdmin && index == _reviewIndex && _selectedIndex != _reviewIndex) {
            _reviewKey.currentState?.reload();
          }
          if (isOwner && index == _myPropertiesIndex && _selectedIndex != _myPropertiesIndex) {
            _myPropertiesKey.currentState?.reload();
          }
          if (index == _appointmentIndex && _selectedIndex != _appointmentIndex) {
            _appointmentKey.currentState?.reload();
          }
          setState(() => _selectedIndex = index);
        },
        indicatorColor: colorScheme.primary.withValues(alpha: 0.2),
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.explore_outlined),
            selectedIcon: Icon(Icons.explore),
            label: 'Khám phá',
          ),
          if (isAdmin)
            const NavigationDestination(
              icon: Icon(Icons.rate_review_outlined),
              selectedIcon: Icon(Icons.rate_review),
              label: 'Duyệt tin',
            ),
          if (isOwner)
            const NavigationDestination(
              icon: Icon(Icons.home_work_outlined),
              selectedIcon: Icon(Icons.home_work),
              label: 'Tin của tôi',
            ),
          const NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            selectedIcon: Icon(Icons.calendar_month),
            label: 'Lịch hẹn',
          ),
          const NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Cá nhân',
          ),
        ],
      ),
    );
  }

  Widget _buildHomeTab(ColorScheme colorScheme) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: SizedBox(
            width: double.infinity,
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment<String>(
                  value: 'sell',
                  label: Text(
                    'Mua Nhà',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  icon: Icon(Icons.sell_outlined),
                ),
                ButtonSegment<String>(
                  value: 'rent',
                  label: Text(
                    'Thuê Nhà',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  icon: Icon(Icons.key_outlined),
                ),
              ],
              selected: {_selectedType},
              onSelectionChanged: (Set<String> newSelection) {
                setState(() {
                  _selectedType = newSelection.first;
                  _fetchData();
                });
              },
              style: SegmentedButton.styleFrom(
                selectedBackgroundColor: colorScheme.primary,
                selectedForegroundColor: Colors.white,
                backgroundColor: Colors.white,
                foregroundColor: colorScheme.primary,
                side: BorderSide(color: colorScheme.primary),
              ),
            ),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _refreshData,
            child: FutureBuilder<List<Property>>(
              future: _futureProperties,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return Center(
                    child: CircularProgressIndicator(
                      color: colorScheme.primary,
                    ),
                  );
                }
                if (snapshot.hasError) {
                  return _buildErrorState(snapshot.error.toString());
                }
                if (!snapshot.hasData || snapshot.data!.isEmpty) {
                  return _buildEmptyState();
                }

                final properties = snapshot.data!;
                return ListView.builder(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 4,
                  ),
                  itemCount: properties.length,
                  itemBuilder: (context, index) => PropertyCard(
                    property: properties[index],
                    properties: properties,
                    index: index,
                  ),
                );
              },
            ),
          ),
        ),
      ],
    );
  }

  void _showAddPropertyDialog(BuildContext context) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => _AddPropertyDialog(
        propertyService: _propertyService,
        onSuccess: () {
          _refreshData();
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Đăng tin thành công, vui lòng chờ duyệt.'),
              backgroundColor: Colors.green,
            ),
          );
        },
      ),
    );
  }

  void _showComingSoon(BuildContext context, String feature) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Chức năng $feature đang phát triển')),
    );
  }

  Widget _buildErrorState(String error) => Center(child: Text(error));

  Widget _buildEmptyState() =>
      const Center(child: Text('Không tìm thấy kết quả'));
}

class _AddPropertyDialog extends StatefulWidget {
  final PropertyService propertyService;
  final VoidCallback onSuccess;

  const _AddPropertyDialog({
    required this.propertyService,
    required this.onSuccess,
  });

  @override
  State<_AddPropertyDialog> createState() => _AddPropertyDialogState();
}

class _AddPropertyDialogState extends State<_AddPropertyDialog> {
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  final _addressCtrl = TextEditingController();
  final _wardCtrl = TextEditingController();
  final _streetCtrl = TextEditingController();
  final _priceCtrl = TextEditingController();
  final _areaCtrl = TextEditingController();
  final _bedsCtrl = TextEditingController();
  final _bathsCtrl = TextEditingController();
  final _legalCtrl = TextEditingController();
  final _priceUnitCtrl = TextEditingController();

  final _titleFocus = FocusNode();
  final _addressFocus = FocusNode();
  final _priceFocus = FocusNode();
  final _areaFocus = FocusNode();

  String _selectedType = 'sell';
  String _selectedCategory = 'apartment';
  String? _selectedDirection;
  int? _selectedDistrictId;
  bool _isLoading = false;
  bool _isLoadingDistricts = true;
  String? _errorMessage;
  List<Map<String, dynamic>> _districts = [];

  static const Map<String, String> _typeLabels = {
    'sell': 'Bán',
    'rent': 'Cho thuê',
  };

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
    'Đông',
    'Tây',
    'Nam',
    'Bắc',
    'Đông Bắc',
    'Đông Nam',
    'Tây Bắc',
    'Tây Nam',
  ];

  @override
  void initState() {
    super.initState();
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
    _legalCtrl.dispose();
    _priceUnitCtrl.dispose();
    _titleFocus.dispose();
    _addressFocus.dispose();
    _priceFocus.dispose();
    _areaFocus.dispose();
    super.dispose();
  }

  Future<void> _loadDistricts() async {
    try {
      final data = await widget.propertyService.getDistricts();
      if (mounted) {
        setState(() {
          _districts = data;
          _isLoadingDistricts = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _isLoadingDistricts = false);
    }
  }

  void _setError(String msg, {FocusNode? focus}) {
    setState(() => _errorMessage = msg);
    focus?.requestFocus();
  }

  Future<void> _submit() async {
    setState(() {
      _errorMessage = null;
      _isLoading = true;
    });

    if (_titleCtrl.text.trim().length < 10) {
      _setError('Tiêu đề phải từ 10 ký tự trở lên', focus: _titleFocus);
      setState(() => _isLoading = false);
      return;
    }
    if (_addressCtrl.text.trim().isEmpty) {
      _setError('Vui lòng nhập địa chỉ', focus: _addressFocus);
      setState(() => _isLoading = false);
      return;
    }
    if (_selectedDistrictId == null) {
      _setError('Vui lòng chọn quận/huyện');
      setState(() => _isLoading = false);
      return;
    }
    final price = double.tryParse(_priceCtrl.text) ?? 0;
    if (price <= 0) {
      _setError('Vui lòng nhập giá hợp lệ (lớn hơn 0)', focus: _priceFocus);
      setState(() => _isLoading = false);
      return;
    }
    final area = double.tryParse(_areaCtrl.text) ?? 0;
    if (area <= 0) {
      _setError(
        'Vui lòng nhập diện tích hợp lệ (lớn hơn 0)',
        focus: _areaFocus,
      );
      setState(() => _isLoading = false);
      return;
    }

    try {
      final result = await widget.propertyService.createProperty({
        'title': _titleCtrl.text.trim(),
        'description': _descCtrl.text.trim(),
        'type': _selectedType,
        'category': _selectedCategory,
        'address': _addressCtrl.text.trim(),
        'ward': _wardCtrl.text.trim(),
        'street': _streetCtrl.text.trim(),
        'price': price,
        'area': area,
        'district_id': _selectedDistrictId,
        'bedrooms': int.tryParse(_bedsCtrl.text),
        'bathrooms': int.tryParse(_bathsCtrl.text),
        'direction': _selectedDirection,
        'legal_status': _legalCtrl.text.trim(),
        'price_unit': _priceUnitCtrl.text.trim().isEmpty
            ? null
            : _priceUnitCtrl.text.trim(),
        'amenities': [],
      });

      if (!mounted) return;
      if (result['success']) {
        Navigator.pop(context);
        widget.onSuccess();
      } else {
        setState(() {
          _errorMessage = result['message'];
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString();
          _isLoading = false;
        });
      }
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
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.88,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(16, 16, 8, 14),
              color: colorScheme.primary,
              child: Row(
                children: [
                  const Icon(Icons.add_business, color: Colors.white),
                  const SizedBox(width: 10),
                  const Expanded(
                    child: Text(
                      'Đăng tin bất động sản',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
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
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
                color: Colors.red[50],
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.error_outline,
                      color: Colors.red,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _errorMessage!,
                        style: const TextStyle(color: Colors.red, fontSize: 13),
                      ),
                    ),
                    GestureDetector(
                      onTap: () => setState(() => _errorMessage = null),
                      child: const Icon(
                        Icons.close,
                        color: Colors.red,
                        size: 18,
                      ),
                    ),
                  ],
                ),
              ),
            Flexible(
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(
                  18,
                  14,
                  18,
                  MediaQuery.of(context).viewInsets.bottom + 20,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _sectionTitle('Thông tin cơ bản'),
                    _field(
                      _titleCtrl,
                      'Tiêu đề (tối thiểu 10 ký tự)',
                      Icons.title,
                      focusNode: _titleFocus,
                    ),
                    _field(
                      _descCtrl,
                      'Mô tả chi tiết',
                      Icons.description,
                      maxLines: 3,
                    ),
                    Row(
                      children: [
                        Expanded(
                          child: _dropdown(
                            'Loại tin',
                            _selectedType,
                            _typeLabels.keys.toList(),
                            labelBuilder: (v) => _typeLabels[v]!,
                            onChanged: (v) =>
                                setState(() => _selectedType = v!),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _dropdown(
                            'Loại BĐS',
                            _selectedCategory,
                            _categoryLabels.keys.toList(),
                            labelBuilder: (v) => _categoryLabels[v]!,
                            onChanged: (v) =>
                                setState(() => _selectedCategory = v!),
                          ),
                        ),
                      ],
                    ),
                    _sectionTitle('Vị trí'),
                    _field(
                      _addressCtrl,
                      'Địa chỉ',
                      Icons.location_on,
                      focusNode: _addressFocus,
                    ),
                    Padding(
                      padding: const EdgeInsets.only(bottom: 14),
                      child: _isLoadingDistricts
                          ? const LinearProgressIndicator()
                          : DropdownButtonFormField<int>(
                              initialValue: _selectedDistrictId,
                              decoration: InputDecoration(
                                prefixIcon: const Icon(
                                  Icons.location_city,
                                  size: 20,
                                ),
                                filled: true,
                                fillColor: Colors.grey[50],
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  borderSide: BorderSide.none,
                                ),
                              ),
                              hint: const Text('Chọn quận/huyện'),
                              items: _districts
                                  .map(
                                    (d) => DropdownMenuItem<int>(
                                      value: d['id'] as int,
                                      child: Text(d['name'] as String),
                                    ),
                                  )
                                  .toList(),
                              isExpanded: true,
                              onChanged: (v) =>
                                  setState(() => _selectedDistrictId = v),
                            ),
                    ),
                    Row(
                      children: [
                        Expanded(
                          child: _field(
                            _streetCtrl,
                            'Tên đường',
                            Icons.add_road,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _field(_wardCtrl, 'Phường/Xã', Icons.map),
                        ),
                      ],
                    ),
                    _sectionTitle('Giá & Diện tích'),
                    Row(
                      children: [
                        Expanded(
                          child: _field(
                            _priceCtrl,
                            'Giá *',
                            Icons.payments,
                            isNumber: true,
                            focusNode: _priceFocus,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _field(
                            _areaCtrl,
                            'Diện tích (m²) *',
                            Icons.square_foot,
                            isNumber: true,
                            focusNode: _areaFocus,
                          ),
                        ),
                      ],
                    ),
                    _field(
                      _priceUnitCtrl,
                      'Đơn giá (VD: Tỷ, Triệu/m², Triệu/tháng)',
                      Icons.label_outline,
                    ),
                    _sectionTitle('Thông tin chi tiết'),
                    Row(
                      children: [
                        Expanded(
                          child: _field(
                            _bedsCtrl,
                            'Phòng ngủ',
                            Icons.bed,
                            isNumber: true,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _field(
                            _bathsCtrl,
                            'Phòng tắm',
                            Icons.bathtub,
                            isNumber: true,
                          ),
                        ),
                      ],
                    ),
                    _dropdown(
                      'Hướng nhà',
                      _selectedDirection,
                      _directions,
                      onChanged: (v) => setState(() => _selectedDirection = v),
                      isOptional: true,
                    ),
                    _field(
                      _legalCtrl,
                      'Pháp lý (VD: Sổ đỏ, Sổ hồng)',
                      Icons.gavel,
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: colorScheme.primary,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 15),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                          elevation: 2,
                        ),
                        onPressed: _isLoading ? null : _submit,
                        child: _isLoading
                            ? const SizedBox(
                                height: 30,
                                width: 30,
                                child: CircularProgressIndicator(
                                  color: Colors.white,
                                  strokeWidth: 2,
                                ),
                              )
                            : const Text(
                                'XÁC NHẬN ĐĂNG TIN',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                ),
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
    child: Text(
      title,
      style: const TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.bold,
        color: Colors.blueGrey,
      ),
    ),
  );

  Widget _field(
    TextEditingController ctrl,
    String hint,
    IconData icon, {
    bool isNumber = false,
    int maxLines = 1,
    FocusNode? focusNode,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextField(
        controller: ctrl,
        focusNode: focusNode,
        maxLines: maxLines,
        keyboardType: isNumber ? TextInputType.number : TextInputType.text,
        decoration: InputDecoration(
          hintText: hint,
          prefixIcon: Icon(icon, size: 20),
          filled: true,
          fillColor: Colors.grey[50],
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 12,
          ),
        ),
      ),
    );
  }

  Widget _dropdown(
    String label,
    String? value,
    List<String> items, {
    required Function(String?) onChanged,
    String Function(String)? labelBuilder,
    bool isOptional = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: DropdownButtonFormField<String>(
        initialValue: value,
        decoration: InputDecoration(
          labelText: label,
          filled: true,
          fillColor: Colors.grey[50],
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
        ),
        items: [
          if (isOptional)
            const DropdownMenuItem<String>(
              value: null,
              child: Text('Không xác định'),
            ),
          ...items.map(
            (e) => DropdownMenuItem<String>(
              value: e,
              child: Text(labelBuilder != null ? labelBuilder(e) : e),
            ),
          ),
        ],
        isExpanded: true,
        onChanged: onChanged,
      ),
    );
  }
}

class PropertyCard extends StatelessWidget {
  final Property property;
  final List<Property> properties;
  final int index;

  const PropertyCard({
    super.key,
    required this.property,
    required this.properties,
    required this.index,
  });

  String _getImageUrl(String url) {
    if (url.startsWith('http')) return url;
    return '${AppConfig.baseAppUrl}/$url';
  }

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
      child: InkWell(
        onTap: () => _openPropertyDetail(context),
        onLongPress: () => _showPropertyActions(context),
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
                        child: const Icon(
                          Icons.broken_image,
                          size: 50,
                          color: Colors.grey,
                        ),
                      ),
                    )
                  : Container(
                      color: Colors.grey[300],
                      child: const Icon(
                        Icons.home_work,
                        size: 50,
                        color: Colors.grey,
                      ),
                    ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    property.title,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '$priceDisplay  •  ${property.area} m²',
                    style: TextStyle(
                      fontSize: 17,
                      color: colorScheme.primary,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      _buildIconLabel(
                        Icons.bed_outlined,
                        '${property.bedrooms ?? 0}',
                      ),
                      const SizedBox(width: 20),
                      _buildIconLabel(
                        Icons.bathtub_outlined,
                        '${property.bathrooms ?? 0}',
                      ),
                      const Spacer(),
                      Icon(
                        Icons.touch_app_outlined,
                        color: colorScheme.primary,
                        size: 18,
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Icon(
                        Icons.location_on_outlined,
                        size: 16,
                        color: colorScheme.primary,
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          property.address,
                          style: const TextStyle(color: Colors.black54),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildIconLabel(IconData icon, String label) {
    return Row(
      children: [
        Icon(icon, size: 18, color: Colors.grey[600]),
        const SizedBox(width: 4),
        Text(
          label,
          style: const TextStyle(
            color: Colors.black87,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  void _openPropertyDetail(BuildContext context) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => PropertyDetailScreen(
          property: property,
          properties: properties,
          initialIndex: index,
        ),
      ),
    );
  }

  void _showPropertyActions(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
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
                const SizedBox(height: 16),
                Text(
                  property.title,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 6),
                Text(
                  'Nhấn giữ để mở thao tác nhanh cho tin này.',
                  style: TextStyle(color: colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: 18),
                _actionTile(
                  context,
                  icon: Icons.visibility_outlined,
                  title: 'Xem chi tiết',
                  subtitle: 'Mở trang thông tin đầy đủ của bất động sản',
                  onTap: () {
                    Navigator.pop(sheetContext);
                    _openPropertyDetail(context);
                  },
                ),
                if (AppConfig.role == 'guest')
                  _actionTile(
                    context,
                    icon: Icons.calendar_month_rounded,
                    title: 'Đặt lịch hẹn',
                    subtitle: 'Mở nhanh màn chi tiết và form đặt lịch',
                    onTap: () {
                      Navigator.pop(sheetContext);
                      _openPropertyDetail(context);
                    },
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _actionTile(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    final colorScheme = Theme.of(context).colorScheme;

    return ListTile(
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: 0, vertical: 4),
      leading: CircleAvatar(
        backgroundColor: colorScheme.primary.withValues(alpha: 0.1),
        child: Icon(icon, color: colorScheme.primary),
      ),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(subtitle),
      trailing: const Icon(Icons.chevron_right_rounded),
    );
  }
}

// ─── Filter Bottom Sheet ───────────────────────────────────────────────────

class _FilterSheet extends StatefulWidget {
  final _PropertyFilter initial;
  final List<Map<String, dynamic>> districts;
  final void Function(_PropertyFilter) onApply;

  const _FilterSheet({
    required this.initial,
    required this.districts,
    required this.onApply,
  });

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  late int? _districtId;
  late String? _category;
  final _minPriceCtrl = TextEditingController();
  final _maxPriceCtrl = TextEditingController();
  final _minAreaCtrl = TextEditingController();
  final _maxAreaCtrl = TextEditingController();

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
  void initState() {
    super.initState();
    _districtId = widget.initial.districtId;
    _category = widget.initial.category;
    _minPriceCtrl.text = widget.initial.minPrice?.toStringAsFixed(0) ?? '';
    _maxPriceCtrl.text = widget.initial.maxPrice?.toStringAsFixed(0) ?? '';
    _minAreaCtrl.text = widget.initial.minArea?.toStringAsFixed(0) ?? '';
    _maxAreaCtrl.text = widget.initial.maxArea?.toStringAsFixed(0) ?? '';
  }

  @override
  void dispose() {
    _minPriceCtrl.dispose();
    _maxPriceCtrl.dispose();
    _minAreaCtrl.dispose();
    _maxAreaCtrl.dispose();
    super.dispose();
  }

  void _reset() {
    setState(() {
      _districtId = null;
      _category = null;
      _minPriceCtrl.clear();
      _maxPriceCtrl.clear();
      _minAreaCtrl.clear();
      _maxAreaCtrl.clear();
    });
  }

  void _apply() {
    widget.onApply(
      _PropertyFilter(
        districtId: _districtId,
        category: _category,
        minPrice: double.tryParse(_minPriceCtrl.text),
        maxPrice: double.tryParse(_maxPriceCtrl.text),
        minArea: double.tryParse(_minAreaCtrl.text),
        maxArea: double.tryParse(_maxAreaCtrl.text),
      ),
    );
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return DraggableScrollableSheet(
      initialChildSize: 0.72,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      expand: false,
      builder: (_, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: Column(
            children: [
              // Handle bar
              Padding(
                padding: const EdgeInsets.only(top: 12, bottom: 4),
                child: Container(
                  width: 48,
                  height: 5,
                  decoration: BoxDecoration(
                    color: Colors.grey[300],
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
              ),
              // Header
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                child: Row(
                  children: [
                    Text(
                      'Bộ lọc',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: colorScheme.onSurface,
                      ),
                    ),
                    const Spacer(),
                    TextButton(
                      onPressed: _reset,
                      child: const Text('Đặt lại'),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1),
              // Scrollable content
              Expanded(
                child: ListView(
                  controller: scrollController,
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                  children: [
                    _sectionLabel('Loại bất động sản'),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: _categoryLabels.entries.map((e) {
                        final selected = _category == e.key;
                        return ChoiceChip(
                          label: Text(e.value),
                          selected: selected,
                          onSelected: (_) =>
                              setState(() => _category = selected ? null : e.key),
                          selectedColor: colorScheme.primary,
                          labelStyle: TextStyle(
                            color: selected ? Colors.white : null,
                            fontWeight:
                                selected ? FontWeight.bold : FontWeight.normal,
                          ),
                          checkmarkColor: Colors.white,
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 20),
                    _sectionLabel('Quận / Huyện'),
                    DropdownButtonFormField<int>(
                      initialValue: _districtId,
                      decoration: InputDecoration(
                        prefixIcon:
                            const Icon(Icons.location_city, size: 20),
                        filled: true,
                        fillColor: Colors.grey[50],
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 12,
                        ),
                      ),
                      isExpanded: true,
                      hint: const Text('Tất cả quận/huyện'),
                      items: [
                        const DropdownMenuItem<int>(
                          value: null,
                          child: Text('Tất cả'),
                        ),
                        ...widget.districts.map(
                          (d) => DropdownMenuItem<int>(
                            value: d['id'] as int,
                            child: Text(d['name'] as String),
                          ),
                        ),
                      ],
                      onChanged: (v) => setState(() => _districtId = v),
                    ),
                    const SizedBox(height: 20),
                    _sectionLabel('Khoảng giá'),
                    Row(
                      children: [
                        Expanded(child: _numberField(_minPriceCtrl, 'Từ')),
                        const Padding(
                          padding: EdgeInsets.symmetric(horizontal: 10),
                          child: Text(
                            '—',
                            style: TextStyle(color: Colors.grey),
                          ),
                        ),
                        Expanded(child: _numberField(_maxPriceCtrl, 'Đến')),
                      ],
                    ),
                    const SizedBox(height: 20),
                    _sectionLabel('Diện tích (m²)'),
                    Row(
                      children: [
                        Expanded(child: _numberField(_minAreaCtrl, 'Từ')),
                        const Padding(
                          padding: EdgeInsets.symmetric(horizontal: 10),
                          child: Text(
                            '—',
                            style: TextStyle(color: Colors.grey),
                          ),
                        ),
                        Expanded(child: _numberField(_maxAreaCtrl, 'Đến')),
                      ],
                    ),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
              // Apply button
              Padding(
                padding: EdgeInsets.fromLTRB(
                  20,
                  8,
                  20,
                  MediaQuery.of(context).viewInsets.bottom + 16,
                ),
                child: SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: colorScheme.primary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    onPressed: _apply,
                    child: const Text(
                      'ÁP DỤNG',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 15,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _sectionLabel(String label) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text(
          label,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.bold,
            color: Colors.blueGrey,
          ),
        ),
      );

  Widget _numberField(TextEditingController ctrl, String hint) => TextField(
        controller: ctrl,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(
          hintText: hint,
          filled: true,
          fillColor: Colors.grey[50],
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 12,
            vertical: 12,
          ),
        ),
      );
}
