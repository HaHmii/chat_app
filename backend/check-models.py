import os
import google.generativeai as genai
from dotenv import load_dotenv

# Đọc API Key từ file .env
load_dotenv()

# Cấu hình thư viện gốc của Google
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("Danh sách các model khả dụng cho API Key của bạn:")
for m in genai.list_models():
    # Chỉ in ra các model có hỗ trợ chat/tạo văn bản (generateContent)
    if 'generateContent' in m.supported_generation_methods:
        # Bỏ đi chữ 'models/' ở đầu để lấy đúng tên slug
        print(f'- {m.name.replace("models/", "")}')