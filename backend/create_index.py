import os
from dotenv import load_dotenv
from llama_index.core import SimpleDirectoryReader
from llama_index.indices.managed.llama_cloud import LlamaCloudIndex

load_dotenv()

# Điền API Key của LlamaCloud vào đây
os.environ["LLAMA_CLOUD_API_KEY"] = os.getenv("LLAMA_CLOUD_API_KEY")

print("Đang đọc các file PDF từ thư mục...")
# Đọc toàn bộ file trong thư mục data_phap_ly
documents = SimpleDirectoryReader("law-data").load_data()

print("Đang tải dữ liệu lên LlamaCloud và tạo Index (quá trình này có thể mất vài phút)...")
# Khởi tạo Index mới toanh trực tiếp bằng code
index = LlamaCloudIndex.from_documents(
    documents,
    "luat-bds-hanoi",       # ĐÂY CHÍNH LÀ TÊN INDEX CỦA BẠN!
    project_name="estate",  # Tên project trên web của bạn
    verbose=True
)

print("Tạo Index thành công! Bây giờ kho dữ liệu 'luat-bds-hanoi' đã sẵn sàng trên Cloud.")