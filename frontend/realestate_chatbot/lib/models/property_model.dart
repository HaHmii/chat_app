class Property {
  final int id;
  final String title;
  final String? description;
  final String type; // 'sell', 'rent'
  final String category; // 'apartment', 'house', 'land', etc.
  final double price;
  final String? priceUnit; // Triệu, Tỷ, Triệu/tháng...
  final double area;
  final String address;
  final String? ward;
  final String? street;
  final int? bedrooms;
  final int? bathrooms;
  final String? direction;
  final String? legalStatus;
  final List<String>? amenities;
  final String? thumbnailUrl;

  Property({
    required this.id,
    required this.title,
    this.description,
    required this.type,
    required this.category,
    required this.price,
    this.priceUnit,
    required this.area,
    required this.address,
    this.ward,
    this.street,
    this.bedrooms,
    this.bathrooms,
    this.direction,
    this.legalStatus,
    this.amenities,
    this.thumbnailUrl,
  });

  factory Property.fromJson(Map<String, dynamic> json) {
    return Property(
      id: json['id'] as int,
      title: json['title'] as String,
      description: json['description'] as String?,
      type: json['type'] as String? ?? 'sell',
      category: json['category'] as String? ?? 'apartment',
      price: double.tryParse(json['price'].toString()) ?? 0.0,
      priceUnit: json['price_unit'] as String?,
      area: double.tryParse(json['area'].toString()) ?? 0.0,
      address: json['address'] as String,
      ward: json['ward'] as String?,
      street: json['street'] as String?,
      bedrooms: json['bedrooms'] as int?,
      bathrooms: json['bathrooms'] as int?,
      direction: json['direction'] as String?,
      legalStatus: json['legal_status'] as String?,
      amenities: json['amenities'] != null ? List<String>.from(json['amenities']) : null,
      thumbnailUrl: json['thumbnail_url'] as String?,
    );
  }
}
