import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../config/app_config.dart';
import '../models/appointment_model.dart';
import '../services/appointment_service.dart';

class AppointmentScreen extends StatefulWidget {
  const AppointmentScreen({super.key});

  @override
  State<AppointmentScreen> createState() => AppointmentScreenState();
}

class AppointmentScreenState extends State<AppointmentScreen> {
  final AppointmentService _appointmentService = AppointmentService();
  late Future<List<Appointment>> _futureAppointments;

  bool get _isGuest => AppConfig.role == 'guest';
  bool get _isOwnerMode =>
      AppConfig.role == 'owner' ||
      AppConfig.role == 'staff' ||
      AppConfig.role == 'admin';

  @override
  void initState() {
    super.initState();
    _futureAppointments = _loadAppointments();
  }

  Future<List<Appointment>> _loadAppointments() {
    if (_isGuest) {
      return _appointmentService.getMyAppointments();
    }
    if (_isOwnerMode) {
      return _appointmentService.getOwnerAppointments();
    }
    return Future.value([]);
  }

  void reload() {
    setState(() {
      _futureAppointments = _loadAppointments();
    });
  }

  void _showSnackBar(String message, {Color? backgroundColor}) {
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: backgroundColor,
      ),
    );
  }

  Future<void> _handleConfirm(Appointment appointment) async {
    final result = await _appointmentService.confirmAppointment(
      appointmentId: appointment.id,
    );

    if (!mounted) return;
    _showSnackBar(
      result['message']?.toString() ?? 'Xác nhận lịch hẹn thành công',
      backgroundColor: result['success'] == true ? Colors.green : null,
    );
    if (result['success'] == true) reload();
  }

  Future<void> _handleCounter(Appointment appointment) async {
    final picked = await _pickDateTime(
      initial: appointment.counterProposedTime ?? appointment.proposedTime,
    );
    if (picked == null) return;

    final result = await _appointmentService.counterAppointment(
      appointmentId: appointment.id,
      counterProposedTime: picked,
    );

    if (!mounted) return;
    _showSnackBar(
      result['message']?.toString() ?? 'Đề xuất lại thời gian thành công',
      backgroundColor: result['success'] == true ? Colors.orange[700] : null,
    );
    if (result['success'] == true) reload();
  }

  Future<void> _handleCancel(Appointment appointment) async {
    final controller = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Hủy lịch hẹn'),
        content: TextField(
          controller: controller,
          maxLines: 3,
          decoration: const InputDecoration(
            labelText: 'Lý do hủy',
            hintText: 'Nhập lý do hủy lịch hẹn',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Đóng'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Xác nhận hủy'),
          ),
        ],
      ),
    );

    if (!mounted || confirmed != true) {
      controller.dispose();
      return;
    }

    final reason = controller.text.trim();
    controller.dispose();

    if (reason.length < 3) {
      _showSnackBar('Vui lòng nhập lý do hủy rõ ràng hơn');
      return;
    }

    final result = await _appointmentService.cancelAppointment(
      appointmentId: appointment.id,
      cancelledBy: 'owner',
      cancelReason: reason,
    );

    if (!mounted) return;
    _showSnackBar(
      result['message']?.toString() ?? 'Hủy lịch hẹn thành công',
      backgroundColor: result['success'] == true ? Colors.red[700] : null,
    );
    if (result['success'] == true) reload();
  }

  Future<DateTime?> _pickDateTime({DateTime? initial}) async {
    final now = DateTime.now();
    final initialDate = initial != null && initial.isAfter(now) ? initial : now;

    final pickedDate = await showDatePicker(
      context: context,
      firstDate: now,
      lastDate: now.add(const Duration(days: 365)),
      initialDate: initialDate,
    );
    if (pickedDate == null || !mounted) return null;

    final pickedTime = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(initialDate),
    );
    if (pickedTime == null) return null;

    final merged = DateTime(
      pickedDate.year,
      pickedDate.month,
      pickedDate.day,
      pickedTime.hour,
      pickedTime.minute,
    );

    if (merged.isBefore(now.add(const Duration(minutes: 30)))) {
      _showSnackBar('Vui lòng chọn thời gian muộn hơn hiện tại ít nhất 30 phút');
      return null;
    }

    return merged;
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return ColoredBox(
      color: colorScheme.surfaceContainerHighest,
      child: RefreshIndicator(
        onRefresh: () async => reload(),
        child: FutureBuilder<List<Appointment>>(
          future: _futureAppointments,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: [
                  SizedBox(height: MediaQuery.of(context).size.height * 0.25),
                  Center(
                    child: CircularProgressIndicator(color: colorScheme.primary),
                  ),
                ],
              );
            }

            if (snapshot.hasError) {
              return ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(24),
                children: [
                  _ErrorState(
                    message: snapshot.error.toString(),
                    onRetry: reload,
                  ),
                ],
              );
            }

            final appointments = snapshot.data ?? [];
            if (appointments.isEmpty) {
              return ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(24),
                children: [_EmptyAppointmentState(isGuest: _isGuest)],
              );
            }

            if (_isGuest) {
              return ListView.builder(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(16, 18, 16, 24),
                itemCount: appointments.length,
                itemBuilder: (context, index) {
                  final appointment = appointments[index];
                  final isLast = index == appointments.length - 1;
                  return _GuestTimelineTile(
                    appointment: appointment,
                    isLast: isLast,
                  );
                },
              );
            }

            return ListView.builder(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 18, 16, 24),
              itemCount: appointments.length,
              itemBuilder: (context, index) {
                final appointment = appointments[index];
                return _OwnerAppointmentCard(
                  appointment: appointment,
                  onConfirm: () => _handleConfirm(appointment),
                  onCounter: () => _handleCounter(appointment),
                  onCancel: () => _handleCancel(appointment),
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class _GuestTimelineTile extends StatelessWidget {
  final Appointment appointment;
  final bool isLast;

  const _GuestTimelineTile({
    required this.appointment,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final statusColor = _statusColor(appointment.status, colorScheme);
    final displayTime =
        appointment.confirmedTime ??
        appointment.counterProposedTime ??
        appointment.proposedTime;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 28,
          child: Column(
            children: [
              Container(
                width: 14,
                height: 14,
                decoration: BoxDecoration(
                  color: statusColor,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: statusColor.withValues(alpha: 0.25),
                      blurRadius: 10,
                      spreadRadius: 2,
                    ),
                  ],
                ),
              ),
              if (!isLast)
                Container(
                  width: 2,
                  height: 126,
                  color: colorScheme.outlineVariant,
                  margin: const EdgeInsets.symmetric(vertical: 4),
                ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Container(
            margin: const EdgeInsets.only(bottom: 18),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.05),
                  blurRadius: 14,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        appointment.propertyTitle ??
                            'Bất động sản #${appointment.propertyId}',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          height: 1.3,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    _StatusChip(status: appointment.status, color: statusColor),
                  ],
                ),
                const SizedBox(height: 12),
                _InfoLine(
                  icon: Icons.schedule_rounded,
                  label: 'Thời gian',
                  value: displayTime != null
                      ? DateFormat('HH:mm - dd/MM/yyyy').format(displayTime)
                      : 'Chưa xác định',
                ),
                if (appointment.note != null && appointment.note!.trim().isNotEmpty) ...[
                  const SizedBox(height: 10),
                  _InfoLine(
                    icon: Icons.sticky_note_2_outlined,
                    label: 'Ghi chú',
                    value: appointment.note!.trim(),
                  ),
                ],
                if (appointment.cancelReason != null &&
                    appointment.cancelReason!.trim().isNotEmpty) ...[
                  const SizedBox(height: 10),
                  _InfoLine(
                    icon: Icons.info_outline,
                    label: 'Lý do',
                    value: appointment.cancelReason!.trim(),
                    valueColor: Colors.red[700],
                  ),
                ],
                const SizedBox(height: 12),
                Text(
                  'Tạo lúc ${DateFormat('HH:mm - dd/MM/yyyy').format(appointment.createdAt ?? DateTime.now())}',
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: 12.5,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _OwnerAppointmentCard extends StatelessWidget {
  final Appointment appointment;
  final VoidCallback onConfirm;
  final VoidCallback onCounter;
  final VoidCallback onCancel;

  const _OwnerAppointmentCard({
    required this.appointment,
    required this.onConfirm,
    required this.onCounter,
    required this.onCancel,
  });

  bool get _canManage =>
      appointment.status == 'pending' || appointment.status == 'counter_proposed';

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final statusColor = _statusColor(appointment.status, colorScheme);

    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 14,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      appointment.propertyTitle ??
                          'Bất động sản #${appointment.propertyId}',
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        height: 1.3,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      appointment.guestName ?? 'Khách #${appointment.guestId}',
                      style: TextStyle(
                        color: colorScheme.onSurfaceVariant,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              _StatusChip(status: appointment.status, color: statusColor),
            ],
          ),
          const SizedBox(height: 14),
          _InfoLine(
            icon: Icons.phone_outlined,
            label: 'Liên hệ',
            value: appointment.guestPhone ?? 'Chưa có số điện thoại',
          ),
          const SizedBox(height: 10),
          _InfoLine(
            icon: Icons.schedule_rounded,
            label: 'Đề xuất',
            value: appointment.proposedTime != null
                ? DateFormat('HH:mm - dd/MM/yyyy').format(appointment.proposedTime!)
                : 'Chưa có',
          ),
          if (appointment.counterProposedTime != null) ...[
            const SizedBox(height: 10),
            _InfoLine(
              icon: Icons.update_rounded,
              label: 'Đề xuất lại',
              value: DateFormat('HH:mm - dd/MM/yyyy').format(appointment.counterProposedTime!),
              valueColor: Colors.orange[700],
            ),
          ],
          if (appointment.confirmedTime != null) ...[
            const SizedBox(height: 10),
            _InfoLine(
              icon: Icons.verified_rounded,
              label: 'Đã chốt',
              value: DateFormat('HH:mm - dd/MM/yyyy').format(appointment.confirmedTime!),
              valueColor: Colors.green[700],
            ),
          ],
          if (appointment.note != null && appointment.note!.trim().isNotEmpty) ...[
            const SizedBox(height: 10),
            _InfoLine(
              icon: Icons.sticky_note_2_outlined,
              label: 'Ghi chú',
              value: appointment.note!.trim(),
            ),
          ],
          if (appointment.cancelReason != null &&
              appointment.cancelReason!.trim().isNotEmpty) ...[
            const SizedBox(height: 10),
            _InfoLine(
              icon: Icons.info_outline,
              label: 'Lý do',
              value: appointment.cancelReason!.trim(),
              valueColor: Colors.red[700],
            ),
          ],
          const SizedBox(height: 16),
          if (_canManage)
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                FilledButton.icon(
                  onPressed: onConfirm,
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('Xác nhận'),
                ),
                OutlinedButton.icon(
                  onPressed: onCounter,
                  icon: const Icon(Icons.schedule_send_outlined),
                  label: const Text('Đề xuất giờ khác'),
                ),
                TextButton.icon(
                  onPressed: onCancel,
                  icon: const Icon(Icons.cancel_outlined),
                  label: const Text('Hủy lịch'),
                  style: TextButton.styleFrom(
                    foregroundColor: Colors.red[700],
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final String status;
  final Color color;

  const _StatusChip({required this.status, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        _statusLabel(status),
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _InfoLine extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;

  const _InfoLine({
    required this.icon,
    required this.label,
    required this.value,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: Colors.blueGrey[400]),
        const SizedBox(width: 10),
        SizedBox(
          width: 80,
          child: Text(
            label,
            style: const TextStyle(color: Colors.black54, fontSize: 13),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              color: valueColor ?? Colors.black87,
              fontWeight: FontWeight.w600,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }
}

class _EmptyAppointmentState extends StatelessWidget {
  final bool isGuest;

  const _EmptyAppointmentState({required this.isGuest});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        children: [
          CircleAvatar(
            radius: 34,
            backgroundColor: colorScheme.primary.withValues(alpha: 0.1),
            child: Icon(
              Icons.calendar_month_rounded,
              color: colorScheme.primary,
              size: 34,
            ),
          ),
          const SizedBox(height: 18),
          Text(
            isGuest
                ? 'Bạn chưa có lịch hẹn nào'
                : 'Chưa có lịch hẹn nào cho tin của bạn',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            isGuest
                ? 'Hãy đặt lịch từ chi tiết bất động sản để theo dõi tiến độ trao đổi với chủ nhà.'
                : 'Khi khách đặt lịch hẹn, bạn sẽ thấy yêu cầu và có thể xác nhận hoặc đề xuất lại tại đây.',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.black54, height: 1.5),
          ),
        ],
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        children: [
          const Icon(Icons.error_outline, color: Colors.red, size: 34),
          const SizedBox(height: 12),
          Text(
            message.replaceFirst('Exception: ', ''),
            textAlign: TextAlign.center,
            style: const TextStyle(height: 1.5),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Tải lại'),
          ),
        ],
      ),
    );
  }
}

Color _statusColor(String status, ColorScheme colorScheme) {
  switch (status) {
    case 'confirmed':
      return Colors.green[700]!;
    case 'counter_proposed':
      return Colors.orange[700]!;
    case 'cancelled':
    case 'expired':
      return Colors.red[700]!;
    case 'done':
      return Colors.teal[700]!;
    default:
      return colorScheme.primary;
  }
}

String _statusLabel(String status) {
  switch (status) {
    case 'confirmed':
      return 'Đã xác nhận';
    case 'counter_proposed':
      return 'Đề xuất lại';
    case 'cancelled':
      return 'Đã hủy';
    case 'done':
      return 'Hoàn tất';
    case 'expired':
      return 'Hết hạn';
    default:
      return 'Chờ phản hồi';
  }
}
