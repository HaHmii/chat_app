class Appointment {
  final int id;
  final int propertyId;
  final String? propertyTitle;
  final int guestId;
  final String? guestName;
  final String? guestPhone;
  final int ownerId;
  final DateTime? proposedTime;
  final DateTime? counterProposedTime;
  final DateTime? confirmedTime;
  final String? note;
  final String status;
  final String? cancelledBy;
  final String? cancelReason;
  final int? rating;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  Appointment({
    required this.id,
    required this.propertyId,
    this.propertyTitle,
    required this.guestId,
    this.guestName,
    this.guestPhone,
    required this.ownerId,
    this.proposedTime,
    this.counterProposedTime,
    this.confirmedTime,
    this.note,
    required this.status,
    this.cancelledBy,
    this.cancelReason,
    this.rating,
    this.createdAt,
    this.updatedAt,
  });

  factory Appointment.fromJson(Map<String, dynamic> json) {
    return Appointment(
      id: json['id'] as int,
      propertyId: json['property_id'] as int,
      propertyTitle: json['property_title'] as String?,
      guestId: json['guest_id'] as int,
      guestName: json['guest_name'] as String?,
      guestPhone: json['guest_phone'] as String?,
      ownerId: json['owner_id'] as int,
      proposedTime: _parseDate(json['proposed_time']),
      counterProposedTime: _parseDate(json['counter_proposed_time']),
      confirmedTime: _parseDate(json['confirmed_time']),
      note: json['note'] as String?,
      status: json['status'] as String? ?? 'pending',
      cancelledBy: json['cancelled_by'] as String?,
      cancelReason: json['cancel_reason'] as String?,
      rating: json['rating'] as int?,
      createdAt: _parseDate(json['created_at']),
      updatedAt: _parseDate(json['updated_at']),
    );
  }

  static DateTime? _parseDate(dynamic value) {
    if (value == null) return null;
    return DateTime.tryParse(value.toString())?.toLocal();
  }
}
