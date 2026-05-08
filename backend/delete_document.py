import os
import gc
from dotenv import load_dotenv
from llama_index.indices.managed.llama_cloud import LlamaCloudIndex

load_dotenv()
os.environ["LLAMA_CLOUD_API_KEY"] = os.getenv("LLAMA_CLOUD_API_KEY")

def delete_only_small_fragments():
    index = None
    try:
        index = LlamaCloudIndex(name="luat-bds-hanoi", project_name="estate")
        target_file = "101-nd.signed.pdf" 
        
        # Ngưỡng dung lượng (ký tự). 
        # Vì bạn chia nhỏ 2000 ký tự, ta để ngưỡng 10,000 là cực kỳ an toàn.
        SIZE_THRESHOLD = 3000 
        
        ref_docs = index.ref_doc_info
        ids_to_delete = []
        
        print(f"--- Đang phân tích Index để tách biệt file lớn và mảnh nhỏ ---")

        for doc_id, info in ref_docs.items():
            if info.metadata.get("file_name") == target_file:
                # Kiểm tra độ dài văn bản (nếu metadata có lưu)
                # Hoặc dùng logic: File lớn sẽ không bao giờ có ID lẻ tẻ nhiều như vậy
                # Ở đây ta sẽ lấy nội dung thực tế để đếm ký tự cho chính xác
                try:
                    # Truy vấn thử nội dung của doc này
                    content_len = len(index.as_retriever().retrieve(doc_id)[0].text) 
                except:
                    # Nếu không truy vấn được, ta dựa vào thông tin node
                    # LlamaCloud thường lưu dung lượng trong metadata nếu bạn có cấu hình
                    content_len = int(info.metadata.get("characters_count", 2000))

                if content_len < SIZE_THRESHOLD:
                    ids_to_delete.append(doc_id)
                else:
                    print(f"🛡️ Phát hiện file LỚN (Size: {content_len:,}). Sẽ GIỮ LẠI ID: {doc_id}")

        if not ids_to_delete:
            print("⚠️ Không tìm thấy các đoạn nhỏ cần xóa.")
            return

        print(f"\n📊 KẾT QUẢ LỌC:")
        print(f"- Số lượng đoạn nhỏ cần xóa: {len(ids_to_delete)}")
        print(f"---")
        
        confirm = input(f"Xác nhận xóa {len(ids_to_delete)} đoạn nhỏ và GIỮ LẠI file lớn? (y/n): ")
        
        if confirm.lower() == 'y':
            for i, doc_id in enumerate(ids_to_delete):
                index.delete_ref_doc(doc_id)
                if (i + 1) % 20 == 0:
                    print(f"Đã xóa {i + 1}/{len(ids_to_delete)}...")
            print("✅ Đã dọn dẹp xong các mảnh nhỏ!")
        else:
            print("❌ Đã hủy.")

    except Exception as e:
        print(f"❌ Lỗi: {e}")
    finally:
        if index is not None:
            del index
        gc.collect()

if __name__ == "__main__":
    delete_only_small_fragments()