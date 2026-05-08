class Property {
  final int id;
  final String title;
  final String? description;
  final String type;
  final String? typeDisplay;
  final String category;
  final String? categoryDisplay;
  final double price;
  final String? priceUnit;
  final String? priceDisplay;
  final double area;
  final String address;
  final String? ward;
  final String? street;
  final String? districtName;
  final int? bedrooms;
  final int? bathrooms;
  final String? direction;
  final String? directionDisplay;
  final String? legalStatus;
  final List<String>? amenities;
  final String? thumbnailUrl;
  final List<String>? images;
  final String? ownerName;
  final String? ownerPhone;
  final DateTime? createdAt;
  final DateTime? expiresAt;
  final int? viewCount;

  const Property({
    required this.id,
    required this.title,
    this.description,
    required this.type,
    this.typeDisplay,
    required this.category,
    this.categoryDisplay,
    required this.price,
    this.priceUnit,
    this.priceDisplay,
    required this.area,
    required this.address,
    this.ward,
    this.street,
    this.districtName,
    this.bedrooms,
    this.bathrooms,
    this.direction,
    this.directionDisplay,
    this.legalStatus,
    this.amenities,
    this.thumbnailUrl,
    this.images,
    this.ownerName,
    this.ownerPhone,
    this.createdAt,
    this.expiresAt,
    this.viewCount,
  });

  factory Property.fromJson(Map<String, dynamic> json) {
    // district có thể là Map {"id":1,"name":"...","short_name":"..."} hoặc null
    final districtRaw = json['district'];
    String? districtName;
    if (districtRaw is Map) {
      districtName = districtRaw['name'] as String?;
    } else if (districtRaw is String) {
      districtName = districtRaw;
    }

    return Property(
      id: json['id'] as int,
      title: json['title'] as String,
      description: json['description'] as String?,
      type: json['type'] as String? ?? 'sell',
      typeDisplay: json['type_display'] as String?,
      category: json['category'] as String? ?? 'apartment',
      categoryDisplay: json['category_display'] as String?,
      price: double.tryParse(json['price'].toString()) ?? 0.0,
      priceUnit: json['price_unit'] as String?,
      priceDisplay: json['price_display'] as String?,
      area: double.tryParse(json['area'].toString()) ?? 0.0,
      address: json['address'] as String? ?? '',
      ward: json['ward'] as String?,
      street: json['street'] as String?,
      districtName: districtName,
      bedrooms: json['bedrooms'] as int?,
      bathrooms: json['bathrooms'] as int?,
      direction: json['direction'] as String?,
      directionDisplay: json['direction_display'] as String?,
      legalStatus: json['legal_status'] as String?,
      amenities: json['amenities'] != null
          ? List<String>.from(json['amenities'] as List)
          : null,
      thumbnailUrl: json['thumbnail_url'] as String?,
      images: json['images'] != null
          ? List<String>.from(json['images'] as List)
          : null,
      ownerName: json['owner_name'] as String?,
      ownerPhone: json['owner_phone'] as String?,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      expiresAt: json['expires_at'] != null
          ? DateTime.tryParse(json['expires_at'] as String)
          : null,
      viewCount: json['view_count'] as int?,
    );
  }
}
