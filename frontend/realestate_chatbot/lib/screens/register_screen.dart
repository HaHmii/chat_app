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
  final _passwordController = TextEditingController();
  final _confirmController = TextEditingController();

  final _authService = AuthService();
  bool _isLoading = false;

  void _handleRegister() async {
    if (_passwordController.text != _confirmController.text) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Mật khẩu xác nhận không khớp!')));
      return;
    }

    setState(() => _isLoading = true);

    final result = await _authService.register(
      fullName: _fullNameController.text.trim(),
      username: _usernameController.text.trim(),
      email: _emailController.text.trim(),
      password: _passwordController.text,
    );

    setState(() => _isLoading = false);

    if (!mounted) return;

    if (result['success']) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Đăng ký thành công! Vui lòng đăng nhập.')));
      Navigator.pop(context); // Quay lại trang đăng nhập
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result['message']), backgroundColor: Colors.red),
      );
    }
  }

  @override
  void dispose() {
    _fullNameController.dispose();
    _usernameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(backgroundColor: Colors.transparent, elevation: 0, iconTheme: const IconThemeData(color: Colors.blue)),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 30),
          child: Column(
            children: [
              const Text('Tạo Tài Khoản Mới', style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
              const SizedBox(height: 10),
              const Text('Điền thông tin để bắt đầu trải nghiệm', style: TextStyle(color: Colors.grey)),
              const SizedBox(height: 30),

              CustomTextField(hintText: 'Họ và tên', icon: Icons.badge, controller: _fullNameController),
              CustomTextField(hintText: 'Tên đăng nhập', icon: Icons.person, controller: _usernameController),
              CustomTextField(hintText: 'Email', icon: Icons.email, controller: _emailController),
              CustomTextField(hintText: 'Mật khẩu', icon: Icons.lock, isPassword: true, controller: _passwordController),
              CustomTextField(hintText: 'Xác nhận mật khẩu', icon: Icons.lock_outline, isPassword: true, controller: _confirmController),

              const SizedBox(height: 20),

              _isLoading
                  ? const CircularProgressIndicator()
                  : PrimaryButton(text: 'ĐĂNG KÝ', onPressed: _handleRegister),
            ],
          ),
        ),
      ),
    );
  }
}