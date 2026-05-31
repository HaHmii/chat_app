#!/usr/bin/env python3
"""
Seed script for properties + property_images tables
- 250 properties across all 30 Hanoi districts
- 3-5 images per property (Unsplash real photos)
- Real GPS coordinates per district
- Covers all types/categories/statuses for multi-turn test coverage
"""

import random
import psycopg2
from datetime import datetime, timedelta

# ─── CONFIG ──────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "realestate_db",   # <-- THAY TÊN DB
    "user": "postgres",                # <-- THAY USER
    "password": "1234",        # <-- THAY PASSWORD
}

TOTAL_PROPERTIES = 250
OWNER_ID_RANGE = (7, 70)

# ─── GPS CENTERS PER DISTRICT (lat, lng) ─────────────────────────────────────
DISTRICT_GPS = {
    1:  (21.0285, 105.8542),   # Hoàn Kiếm
    2:  (21.0358, 105.8412),   # Ba Đình
    3:  (21.0607, 105.8216),   # Tây Hồ
    4:  (21.0080, 105.8680),   # Hai Bà Trưng
    5:  (21.0313, 105.7908),   # Cầu Giấy
    6:  (21.0207, 105.8390),   # Đống Đa
    7:  (20.9940, 105.8130),   # Thanh Xuân
    8:  (20.9812, 105.8596),   # Hoàng Mai
    9:  (21.0469, 105.9087),   # Long Biên
    10: (20.9760, 105.7810),   # Nam Từ Liêm
    11: (21.0610, 105.7753),   # Bắc Từ Liêm
    12: (20.9594, 105.7756),   # Hà Đông
    13: (21.1336, 105.5053),   # Sơn Tây
    14: (21.1879, 105.3297),   # Ba Vì
    15: (21.1028, 105.6469),   # Phúc Thọ
    16: (21.0869, 105.6934),   # Đan Phượng
    17: (21.0079, 105.7286),   # Hoài Đức
    18: (20.9544, 105.6384),   # Quốc Oai
    19: (21.0105, 105.5730),   # Thạch Thất
    20: (20.9218, 105.7244),   # Chương Mỹ
    21: (20.9012, 105.7767),   # Thanh Oai
    22: (20.8633, 105.8534),   # Thường Tín
    23: (20.7789, 105.8441),   # Phú Xuyên
    24: (20.7175, 105.7808),   # Ứng Hòa
    25: (20.6569, 105.7239),   # Mỹ Đức
    26: (21.1756, 105.8439),   # Mê Linh
    27: (21.1457, 105.9028),   # Đông Anh
    28: (21.0022, 105.9462),   # Gia Lâm
    29: (21.2490, 105.8400),   # Sóc Sơn
    30: (20.9254, 105.8628),   # Thanh Trì
}

DISTRICT_NAMES = {
    1: "Hoàn Kiếm", 2: "Ba Đình", 3: "Tây Hồ", 4: "Hai Bà Trưng",
    5: "Cầu Giấy", 6: "Đống Đa", 7: "Thanh Xuân", 8: "Hoàng Mai",
    9: "Long Biên", 10: "Nam Từ Liêm", 11: "Bắc Từ Liêm", 12: "Hà Đông",
    13: "Sơn Tây", 14: "Ba Vì", 15: "Phúc Thọ", 16: "Đan Phượng",
    17: "Hoài Đức", 18: "Quốc Oai", 19: "Thạch Thất", 20: "Chương Mỹ",
    21: "Thanh Oai", 22: "Thường Tín", 23: "Phú Xuyên", 24: "Ứng Hòa",
    25: "Mỹ Đức", 26: "Mê Linh", 27: "Đông Anh", 28: "Gia Lâm",
    29: "Sóc Sơn", 30: "Thanh Trì",
}

# ─── DATA POOLS ───────────────────────────────────────────────────────────────
PROPERTY_TYPES = ['sell', 'rent']
PROPERTY_CATEGORIES = ['apartment', 'house', 'land', 'villa', 'townhouse', 'shophouse', 'office']
PROPERTY_STATUSES = ['approved', 'approved', 'approved', 'pending', 'sold', 'hidden']  # weighted

DIRECTIONS = ['Đông', 'Tây', 'Nam', 'Bắc', 'Đông Nam', 'Đông Bắc', 'Tây Nam', 'Tây Bắc']

WARDS = {
    1:  ["Hàng Bạc", "Hàng Gai", "Hàng Đào", "Lý Thái Tổ", "Tràng Tiền"],
    2:  ["Ngọc Hà", "Đội Cấn", "Liễu Giai", "Kim Mã", "Nguyễn Trung Trực"],
    3:  ["Quảng An", "Tứ Liên", "Nhật Tân", "Xuân La", "Bưởi"],
    4:  ["Bạch Đằng", "Bùi Thị Xuân", "Đống Mác", "Lê Đại Hành", "Thanh Lương"],
    5:  ["Dịch Vọng", "Dịch Vọng Hậu", "Nghĩa Đô", "Quan Hoa", "Trung Hoà"],
    6:  ["Cát Linh", "Hàng Bột", "Khâm Thiên", "Nam Đồng", "Văn Miếu"],
    7:  ["Hạ Đình", "Kim Giang", "Nhân Chính", "Phương Liệt", "Thanh Xuân Bắc"],
    8:  ["Đại Kim", "Định Công", "Hoàng Liệt", "Lĩnh Nam", "Tân Mai"],
    9:  ["Bồ Đề", "Đức Giang", "Gia Thụy", "Long Biên", "Ngọc Lâm"],
    10: ["Cầu Diễn", "Đại Mỗ", "Mỹ Đình", "Phú Đô", "Tây Mỗ"],
    11: ["Cổ Nhuế", "Đông Ngạc", "Liên Mạc", "Thượng Cát", "Xuân Đỉnh"],
    12: ["Dương Nội", "Hà Cầu", "Kiến Hưng", "Mộ Lao", "Văn Quán"],
}

STREETS = [
    "Lê Duẩn", "Nguyễn Huệ", "Hoàng Diệu", "Đinh Tiên Hoàng",
    "Trần Phú", "Nguyễn Trãi", "Lê Lợi", "Hai Bà Trưng",
    "Trường Chinh", "Giải Phóng", "Láng Hạ", "Kim Mã",
    "Xuân Thủy", "Phạm Văn Đồng", "Nguyễn Văn Cừ", "Cầu Giấy",
    "Tố Hữu", "Lê Văn Lương", "Nguyễn Xiển", "Định Công",
]

# Titles templates per category
TITLE_TEMPLATES = {
    "apartment": [
        "Căn hộ {rooms} phòng ngủ {district} view đẹp",
        "Chung cư cao cấp {district} full nội thất",
        "Căn hộ studio {district} gần trung tâm",
        "Căn hộ {area}m² {district} thoáng mát",
        "Căn hộ {rooms}PN tại {district} giá tốt",
    ],
    "house": [
        "Nhà phố {district} {area}m² sổ đỏ chính chủ",
        "Nhà riêng {rooms} tầng {district} ngõ thông",
        "Nhà {area}m² mặt tiền đường lớn {district}",
        "Nhà phân lô {district} ô tô đỗ cửa",
    ],
    "land": [
        "Đất nền {district} {area}m² thổ cư 100%",
        "Lô đất {district} mặt tiền {street}",
        "Đất {area}m² {district} quy hoạch rõ ràng",
        "Bán đất {district} gần khu đô thị mới",
    ],
    "villa": [
        "Biệt thự {district} {area}m² sân vườn rộng",
        "Villa song lập {district} thiết kế hiện đại",
        "Biệt thự nghỉ dưỡng {district} view hồ",
        "Biệt thự {rooms}PN {district} nội thất cao cấp",
    ],
    "townhouse": [
        "Nhà liền kề {district} {area}m² xây mới",
        "Liền kề {district} kinh doanh được tầng 1",
        "Nhà liền kề {rooms} tầng {district} ô tô vào nhà",
    ],
    "shophouse": [
        "Shophouse {district} mặt tiền kinh doanh sầm uất",
        "Nhà mặt phố {district} {area}m² vị trí vàng",
        "Shophouse {rooms} tầng {district} cho thuê tốt",
    ],
    "office": [
        "Văn phòng {district} {area}m² view panorama",
        "Cho thuê văn phòng {district} đủ tiện nghi",
        "Văn phòng hạng B {district} giao thông thuận tiện",
        "Office {area}m² tại tòa nhà {district}",
    ],
}

DESCRIPTIONS = [
    "Bất động sản vị trí đắc địa, giao thông thuận tiện, gần trường học, bệnh viện, siêu thị. Pháp lý rõ ràng, sổ đỏ chính chủ.",
    "Căn hộ thiết kế hiện đại, thoáng mát, ban công view đẹp. Nội thất đầy đủ cao cấp, sẵn sàng dọn vào ở ngay.",
    "Vị trí trung tâm, kết nối dễ dàng các trục đường lớn. Hàng xóm văn minh, an ninh 24/7, môi trường sống lý tưởng.",
    "Bất động sản đầu tư tiềm năng, khu vực đang phát triển mạnh. Giá hợp lý, có thể thương lượng với người mua thiện chí.",
    "Thiết kế thông minh tối ưu diện tích. Hệ thống điện nước mới, sơn mới toàn bộ. Phù hợp cả để ở lẫn cho thuê.",
    "Căn góc 2 mặt thoáng, đón nắng gió tự nhiên. Gần công viên, hồ điều hòa. Cộng đồng dân cư văn minh, đồng đẳng.",
    "Nhà xây kiên cố, móng cọc, tường gạch đặc. Mái tôn lạnh chống nóng. Phù hợp gia đình nhiều thế hệ.",
    "Pháp lý minh bạch, sổ đỏ từng căn. Hạ tầng đồng bộ, điện âm tường, nước máy thành phố. Giao ngay sau khi ký hợp đồng.",
]

# Unsplash image pools by category
IMAGE_POOLS = {
    "apartment": [
        "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800",
        "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800",
        "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800",
        "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=800",
        "https://images.unsplash.com/photo-1554995207-c18c203602cb?w=800",
        "https://images.unsplash.com/photo-1600607687939-ce8a6f349c57?w=800",
        "https://images.unsplash.com/photo-1600566753376-12c8ab7fb75b?w=800",
        "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800",
    ],
    "house": [
        "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=800",
        "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800",
        "https://images.unsplash.com/photo-1598228723793-52759bba239c?w=800",
        "https://images.unsplash.com/photo-1523217582562-09d0def993a6?w=800",
        "https://images.unsplash.com/photo-1513584684374-8bab748fbf90?w=800",
        "https://images.unsplash.com/photo-1555636222-cae831e670b3?w=800",
    ],
    "land": [
        "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=800",
        "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=800",
        "https://images.unsplash.com/photo-1448375240586-882707db888b?w=800",
        "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800",
    ],
    "villa": [
        "https://images.unsplash.com/photo-1613490493576-7fde63acd811?w=800",
        "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800",
        "https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?w=800",
        "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?w=800",
        "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800",
    ],
    "townhouse": [
        "https://images.unsplash.com/photo-1486325212027-8081e485255e?w=800",
        "https://images.unsplash.com/photo-1575517111839-3a3843ee7f5d?w=800",
        "https://images.unsplash.com/photo-1600585154526-990dced4db0d?w=800",
    ],
    "shophouse": [
        "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=800",
        "https://images.unsplash.com/photo-1519642918688-7e43b19245d8?w=800",
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=800",
    ],
    "office": [
        "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800",
        "https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=800",
        "https://images.unsplash.com/photo-1604328698692-f76ea9498e76?w=800",
        "https://images.unsplash.com/photo-1568992687947-868a62a9f521?w=800",
    ],
}

# ─── PRICE RANGES by type + category ─────────────────────────────────────────
PRICE_CONFIG = {
    # (min, max, unit)
    ("sell", "apartment"):   (800_000_000,   8_000_000_000,  "VND"),
    ("sell", "house"):       (2_000_000_000, 15_000_000_000, "VND"),
    ("sell", "land"):        (500_000_000,   10_000_000_000, "VND"),
    ("sell", "villa"):       (5_000_000_000, 50_000_000_000, "VND"),
    ("sell", "townhouse"):   (3_000_000_000, 20_000_000_000, "VND"),
    ("sell", "shophouse"):   (4_000_000_000, 30_000_000_000, "VND"),
    ("sell", "office"):      (5_000_000_000, 40_000_000_000, "VND"),
    ("rent", "apartment"):   (5_000_000,     30_000_000,     "VND/tháng"),
    ("rent", "house"):       (10_000_000,    50_000_000,     "VND/tháng"),
    ("rent", "land"):        (3_000_000,     20_000_000,     "VND/tháng"),
    ("rent", "villa"):       (30_000_000,    150_000_000,    "VND/tháng"),
    ("rent", "townhouse"):   (15_000_000,    60_000_000,     "VND/tháng"),
    ("rent", "shophouse"):   (20_000_000,    100_000_000,    "VND/tháng"),
    ("rent", "office"):      (15_000_000,    80_000_000,     "VND/tháng"),
}

AREA_CONFIG = {
    "apartment":  (30,  150),
    "house":      (40,  300),
    "land":       (50,  1000),
    "villa":      (200, 1500),
    "townhouse":  (60,  250),
    "shophouse":  (50,  300),
    "office":     (30,  500),
}

BEDROOM_CONFIG = {
    "apartment":  (1, 4),
    "house":      (2, 6),
    "land":       None,
    "villa":      (3, 8),
    "townhouse":  (3, 6),
    "shophouse":  (2, 5),
    "office":     None,
}

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def rand_gps(district_id):
    lat, lng = DISTRICT_GPS.get(district_id, (21.0245, 105.8412))
    # ±0.015 degree (~1.5km spread)
    lat += random.uniform(-0.015, 0.015)
    lng += random.uniform(-0.015, 0.015)
    return f"{lat:.6f},{lng:.6f}"

def rand_price(ptype, category):
    key = (ptype, category)
    lo, hi, unit = PRICE_CONFIG.get(key, (1_000_000_000, 5_000_000_000, "VND"))
    # round to nearest 50M for sell, 500K for rent
    step = 50_000_000 if ptype == "sell" else 500_000
    price = random.randint(lo // step, hi // step) * step
    return price, unit

def rand_area(category):
    lo, hi = AREA_CONFIG.get(category, (50, 200))
    return round(random.uniform(lo, hi), 2)

def rand_rooms(category):
    cfg = BEDROOM_CONFIG.get(category)
    if cfg is None:
        return None, None
    bedrooms = random.randint(*cfg)
    bathrooms = max(1, bedrooms - random.randint(0, 1))
    return bedrooms, bathrooms

def rand_ward(district_id):
    wards = WARDS.get(district_id)
    if wards:
        return random.choice(wards)
    return f"Phường {random.randint(1, 10)}"

def make_title(category, district_id, area, rooms):
    templates = TITLE_TEMPLATES.get(category, ["{category} {district}"])
    tpl = random.choice(templates)
    district_name = DISTRICT_NAMES[district_id]
    street = random.choice(STREETS)
    return tpl.format(
        rooms=rooms or 2,
        district=district_name,
        area=int(area),
        street=street,
        category=category,
    )

def rand_date():
    days_ago = random.randint(0, 180)
    return datetime.now() - timedelta(days=days_ago)

# ─── MAIN SEED ────────────────────────────────────────────────────────────────
def seed():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    properties_inserted = 0
    images_inserted = 0

    district_ids = list(range(1, 31))

    for i in range(TOTAL_PROPERTIES):
        district_id = random.choice(district_ids)
        ptype       = random.choice(PROPERTY_TYPES)
        category    = random.choice(PROPERTY_CATEGORIES)
        status      = random.choice(PROPERTY_STATUSES)
        owner_id    = random.randint(*OWNER_ID_RANGE)
        area        = rand_area(category)
        price, price_unit = rand_price(ptype, category)
        bedrooms, bathrooms = rand_rooms(category)
        direction   = random.choice(DIRECTIONS)
        ward        = rand_ward(district_id)
        street      = random.choice(STREETS)
        district_name = DISTRICT_NAMES[district_id]
        address     = f"{random.randint(1,200)} {street}, {ward}, {district_name}, Hà Nội"
        gps         = rand_gps(district_id)
        title       = make_title(category, district_id, area, bedrooms)
        description = random.choice(DESCRIPTIONS)
        created_at  = rand_date()
        updated_at  = created_at + timedelta(hours=random.randint(0, 48))
        rejection_reason = None
        if status == "rejected":
            rejection_reason = "Thông tin không đầy đủ hoặc không chính xác."

        cur.execute("""
            INSERT INTO public.properties
                (owner_id, district_id, title, description, type, category, status,
                 address, ward, street, price, area, bedrooms, bathrooms,
                 direction, rejection_reason, created_at, updated_at, price_unit, gps)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            owner_id, district_id, title, description, ptype, category, status,
            address, ward, street, price, area, bedrooms, bathrooms,
            direction, rejection_reason, created_at, updated_at, price_unit, gps,
        ))

        property_id = cur.fetchone()[0]
        properties_inserted += 1

        # ── Images: 3-5 per property ────────────────────────────────────────
        pool = IMAGE_POOLS.get(category, IMAGE_POOLS["apartment"])
        num_images = random.randint(3, min(5, len(pool)))
        chosen_imgs = random.sample(pool, num_images)

        for sort_order, url in enumerate(chosen_imgs):
            cur.execute("""
                INSERT INTO public.property_images (property_id, url, sort_order)
                VALUES (%s, %s, %s)
            """, (property_id, url, sort_order))
            images_inserted += 1

        if (i + 1) % 50 == 0:
            conn.commit()
            print(f"  ✓ {i + 1}/{TOTAL_PROPERTIES} properties seeded...")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n✅ Done!")
    print(f"   Properties inserted : {properties_inserted}")
    print(f"   Images inserted     : {images_inserted}")
    print(f"   Avg images/property : {images_inserted/properties_inserted:.1f}")


if __name__ == "__main__":
    print("🌱 Seeding Hanoi real estate data...")
    seed()