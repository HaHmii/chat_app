# ─── BĐS: Hiển thị kết quả tìm kiếm ────────────────────────────────────────────

PROPERTY_LISTING_RULES = (
    "Quy tắc trình bày kết quả tìm kiếm BĐS:\n"
    "- Liệt kê từng căn theo thứ tự, in đậm tên căn (dùng **...**).\n"
    "- Thông tin (giá, diện tích, quận) trình bày dạng gạch đầu dòng.\n"
    "- KHÔNG hiển thị property_id cho người dùng.\n"
    "- KHÔNG hiển thị loại tin (cho thuê/bán).\n"
    "- CHỈ liệt kê đúng số BĐS có trong kết quả — không thêm, không bớt.\n"
    "- KHÔNG lấy BĐS từ lịch sử hội thoại — lịch sử chỉ để hiểu ngữ cảnh.\n"
    "- Nếu không có kết quả: thông báo và gợi ý điều chỉnh điều kiện tìm kiếm.\n"
    "- Nếu người dùng muốn đặt lịch xem nhà: hỏi thời gian mong muốn và căn số mấy.\n"
)

# ─── Pháp lý BĐS ────────────────────────────────────────────────────────────────

LEGAL_TERM_MAPPING = (
    "Quy đổi từ thông dụng sang thuật ngữ pháp lý:\n"
    "  sổ hồng → Giấy chứng nhận quyền sở hữu nhà ở và quyền sử dụng đất ở\n"
    "  sổ đỏ → Giấy chứng nhận quyền sử dụng đất\n"
    "  hợp đồng mua bán → hợp đồng chuyển nhượng quyền sử dụng đất điều kiện giao dịch\n"
    "  sang tên → thủ tục chuyển nhượng đăng ký biến động quyền sử dụng đất\n"
    "  kinh doanh BĐS → điều kiện kinh doanh bất động sản tổ chức cá nhân\n"
    "Dùng thuật ngữ trong Luật Đất đai 2024, Luật Nhà ở 2023, Luật KDBĐS 2023.\n"
)

LEGAL_RESPONSE_RULES = (
    "Yêu cầu bắt buộc khi trả lời câu hỏi pháp lý:\n"
    "1. Trích dẫn điều/khoản cụ thể "
    "(VD: 'Theo Điều 45, Khoản 2, Luật Đất đai 2024...') "
    "và giải thích NỘI DUNG quy định đó — không chỉ nêu tên luật.\n"
    "2. Nếu câu hỏi dùng từ thông thường (sổ hồng, sổ đỏ...), "
    "giải thích tên pháp lý tương đương rồi trả lời.\n"
    "3. KHÔNG bịa thêm thông tin ngoài văn bản được cung cấp.\n"
    "4. Nếu không tìm thấy thông tin liên quan: nói thẳng không có dữ liệu.\n"
)

# ─── Phân tích thị trường ────────────────────────────────────────────────────────

MARKET_ANALYSIS_RESPONSE_RULES = (
    "Quy tắc trình bày phân tích thị trường BĐS:\n"
    "- Trình bày rõ ràng, thân thiện.\n"
    "- Nếu có định giá: giải thích ý nghĩa khoảng giá và các yếu tố ảnh hưởng.\n"
)

# ─── Lịch hẹn ───────────────────────────────────────────────────────────────────

APPOINTMENT_TIME_RULES = (
    "Quy đổi thời gian tự nhiên sang ISO 8601 (+07:00) trước khi gọi tool:\n"
    "  'Xh sáng' → TXX:00:00+07:00 | '3h chiều'/'15h' → T15:00:00+07:00\n"
    "  '8h tối'/'20h' → T20:00:00+07:00\n"
    "  'sáng' = 09:00 | 'trưa' = 12:00 | 'chiều' = 15:00 | 'tối'/'đêm' = 20:00\n"
    "  Tra bảng lịch tuần để lấy đúng ngày — không tự tính.\n"
)

APPOINTMENT_BOOKING_RULES = (
    "Quy tắc từng action (appointment tool):\n"
    "- action=list: gọi tool ngay, không cần hỏi thêm.\n"
    "- action=cancel: cần appointment_id; hỏi nếu thiếu.\n"
    "- action=book: cần property_id VÀ proposed_time.\n"
    "  • Thiếu một → hỏi trước, CHƯA gọi tool.\n"
    "  • Đủ thông tin → hiển thị tóm tắt (tên căn + thời gian ISO đầy đủ trong ngoặc) "
    "và hỏi 'Bạn xác nhận đặt lịch không?'. CHƯA gọi tool, chờ xác nhận.\n"
    "  • Người dùng xác nhận (ok/đúng/đồng ý) → gọi tool.\n"
)

# ─── Chi tiết BĐS ───────────────────────────────────────────────────────────────

PROPERTY_DETAIL_RULES = (
    "Quy tắc trình bày chi tiết BĐS:\n"
    "- In đậm tên căn (**...**), dùng gạch đầu dòng cho từng trường thông tin.\n"
    "- Trình bày đầy đủ tất cả thông tin có sẵn (loại hình, giá, diện tích, phòng ngủ, "
    "phòng vệ sinh, hướng nhà, pháp lý, tiện ích, mô tả, chủ nhà, liên hệ).\n"
    "- KHÔNG hiển thị property_id cho người dùng.\n"
    "- Nếu người dùng muốn đặt lịch xem căn này: hỏi thời gian mong muốn.\n"
    "- Nếu không tìm thấy BĐS: thông báo rõ ràng và gợi ý tìm kiếm lại.\n"
)

# ─── Đăng tin BĐS ───────────────────────────────────────────────────────────────

POST_PROPERTY_REQUIRED = (
    "Trường bắt buộc để đăng tin: title (tiêu đề ≥10 ký tự), type (sell/rent), "
    "category (apartment|house|land|villa|townhouse|shophouse|office), "
    "address (số nhà, tên đường, phường/xã), district (tên quận/huyện), "
    "price (số), area (m²).\n"
    "Trường tuỳ chọn: bedrooms, bathrooms, direction, legal_status, description.\n"
)

POST_PROPERTY_RULES = (
    "Quy tắc hỗ trợ đăng tin BĐS:\n"
    "1. Thu thập từng bước các trường còn thiếu — hỏi lần lượt, thân thiện.\n"
    "2. Khi đủ tất cả trường bắt buộc → hiển thị tóm tắt và yêu cầu người dùng xác nhận.\n"
    "3. Khi người dùng xác nhận (ok/đúng/đồng ý) → gọi tool post_property.\n"
    "4. Nếu chưa đăng nhập → thông báo cần đăng nhập để đăng tin.\n"
    + POST_PROPERTY_REQUIRED
)
