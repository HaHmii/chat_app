import 'package:flutter/material.dart';
import '../widgets/custom_text_field.dart';
import '../widgets/primary_button.dart';
import '../services/auth_service.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _fullNameController = TextEditingController();
  final _usernameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();

  final _authService = AuthService();
  bool _isLoading = false;
  String? _selectedRole; // 'user' hoặc 'owner'

  void _handleRegister() async {
    if (_selectedRole == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Vui lòng chọn nhu cầu của bạn!')),
      );
      return;
    }

    if (_phoneController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Vui lòng nhập số điện thoại!')),
      );
      return;
    }

    if (_phoneController.text.trim().length < 9) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Số điện thoại không hợp lệ!')),
      );
      return;
    }

    if (_passwordController.text != _confirmController.text) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Mật khẩu xác nhận không khớp!')),
      );
      return;
    }

    setState(() => _isLoading = true);

    try {
      final result = await _authService.register(
        fullName: _fullNameController.text.trim(),
        username: _usernameController.text.trim(),
        email: _emailController.text.trim(),
        phoneNumber: _phoneController.text.trim(),
        password: _passwordController.text,
        role: _selectedRole!,
      );

      if (!mounted) return;

      if (result['success']) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Đăng ký thành công! Vui lòng đăng nhập.')),
        );
        Navigator.pop(context);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(result['message']), backgroundColor: Colors.red),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Lỗi kết nối: $e'), backgroundColor: Colors.red),
      );
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  void dispose() {
    _fullNameController.dispose();
    _usernameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.blue),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 30),
          child: Column(
            children: [
              const Text(
                'Tạo Tài Khoản Mới',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 10),
              const Text(
                'Điền thông tin để bắt đầu trải nghiệm',
                style: TextStyle(color: Colors.grey),
              ),
              const SizedBox(height: 30),

              CustomTextField(
                hintText: 'Họ và tên',
                icon: Icons.badge,
                controller: _fullNameController,
              ),
              CustomTextField(
                hintText: 'Tên đăng nhập',
                icon: Icons.person,
                controller: _usernameController,
              ),
              CustomTextField(
                hintText: 'Email',
                icon: Icons.email,
                controller: _emailController,
              ),
              CustomTextField(
                hintText: 'Số điện thoại',
                icon: Icons.phone,
                controller: _phoneController,
              ),
              CustomTextField(
                hintText: 'Mật khẩu',
                icon: Icons.lock,
                isPassword: true,
                controller: _passwordController,
              ),
              CustomTextField(
                hintText: 'Xác nhận mật khẩu',
                icon: Icons.lock_outline,
                isPassword: true,
                controller: _confirmController,
              ),

              const SizedBox(height: 8),

              // --- Chọn nhu cầu ---
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Nhu cầu của bạn là gì?',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: Colors.grey[800],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: _RoleCard(
                      icon: Icons.search_rounded,
                      title: 'Tìm mua / thuê',
                      subtitle: 'Tôi muốn tìm bất động sản',
                      selected: _selectedRole == 'user',
                      selectedColor: colorScheme.primary,
                      onTap: () => setState(() => _selectedRole = 'user'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _RoleCard(
                      icon: Icons.home_work_rounded,
                      title: 'Bán / cho thuê',
                      subtitle: 'Tôi muốn đăng tin bất động sản',
                      selected: _selectedRole == 'owner',
                      selectedColor: Colors.green[700]!,
                      onTap: () => setState(() => _selectedRole = 'owner'),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 28),

              _isLoading
                  ? const CircularProgressIndicator()
                  : PrimaryButton(text: 'ĐĂNG KÝ', onPressed: _handleRegister),

              const SizedBox(height: 20),
            ],
          ),
        ),
      ),
    );
  }
}

class _RoleCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool selected;
  final Color selectedColor;
  final VoidCallback onTap;

  const _RoleCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.selectedColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
        decoration: BoxDecoration(
          color: selected ? selectedColor.withValues(alpha: 0.08) : Colors.grey[50],
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: selected ? selectedColor : Colors.grey[300]!,
            width: selected ? 2 : 1,
          ),
        ),
        child: Column(
          children: [
            Icon(
              icon,
              size: 32,
              color: selected ? selectedColor : Colors.grey[400],
            ),
            const SizedBox(height: 8),
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.bold,
                color: selected ? selectedColor : Colors.grey[700],
              ),
            ),
            const SizedBox(height: 4),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 11,
                color: selected ? selectedColor.withValues(alpha: 0.8) : Colors.grey[500],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
