import os
import atexit
import sqlalchemy
import warnings
import time
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from llama_index.indices.managed.llama_cloud import LlamaCloudIndex
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage, SystemMessage

# Tắt các cảnh báo không cần thiết
warnings.filterwarnings("ignore")
load_dotenv()

# Định nghĩa màu sắc cho Terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    CYAN = '\033[96m'

# 1. Cấu hình Model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

# 2. Thiết lập Công cụ Truy xuất Pháp luật
legal_index = LlamaCloudIndex(
    name="luat-bds-hanoi", 
    project_name="estate",
    api_key=os.getenv("LLAMA_CLOUD_API_KEY")
)
legal_retriever = legal_index.as_retriever(similarity_top_k=3)

@tool
def legal_lookup(query: str) -> str:
    """Tra cứu pháp luật, thủ tục sang tên sổ đỏ, thuế phí và quy định cọc căn hộ Hà Nội."""
    nodes = legal_retriever.retrieve(query)
    return "\n\n---\n\n".join([node.get_content() for node in nodes])

# 3. Thiết lập Công cụ Truy xuất Căn hộ (SQLAlchemy Thuần túy)
engine = sqlalchemy.create_engine(os.getenv("POSTGRES_URI"))

@tool
def apartment_search(user_query: str) -> str:
    """Tìm kiếm căn hộ từ database theo giá, vị trí và diện tích thực tế tại Hà Nội."""
    schema_info = """
      Bảng 'apartments' gồm: 
        title (tiêu đề), 
        address (địa chỉ), 
        price_num (giá số), 
        price_unit (đơn vị giá: 'tỷ' cho bán, 'triệu/tháng' cho thuê), 
        area_num (m2), 
        bedrooms_num (phòng ngủ), 
        listing_type (sale/rent).
      Đối với truy vấn address, hãy sử dụng ILIKE '%keyword%' để tìm kiếm gần đúng.
    """
    prompt = f"Viết 1 câu lệnh SQL PostgreSQL cho yêu cầu: '{user_query}' dựa trên: {schema_info}. Chỉ trả về code SQL."
    
    try:
        sql_response = llm.invoke(prompt)
        sql_command = sql_response.content.strip().replace("```sql", "").replace("```", "").replace(";", "")
        
        # In ngầm để debug nếu cần, nhưng định dạng nhỏ gọn
        print(f"{Colors.YELLOW}  [System SQL]: {sql_command}{Colors.END}")

        with engine.connect() as connection:
            result = connection.execute(sqlalchemy.text(sql_command))
            rows = result.fetchall()
            return "\n".join([str(row) for row in rows]) if rows else "Không tìm thấy dữ liệu."
    except Exception as e:
        return f"Lỗi truy vấn: {e}"

# 4. XÂY DỰNG AGENT BẰNG LANGGRAPH THUẦN
tools = [legal_lookup, apartment_search]
llm_with_tools = llm.bind_tools(tools)

# Định nghĩa Node "Bộ não"
def assistant_node(state: MessagesState):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# Khởi tạo bản đồ StateGraph
workflow = StateGraph(MessagesState)

# Thêm các Node (Trạm dừng)
workflow.add_node("assistant", assistant_node)
workflow.add_node("tools", ToolNode(tools)) # Node công cụ dựng sẵn của LangGraph

# Kết nối các Node (Đường đi)
workflow.add_edge(START, "assistant")
# Nếu AI cần tool thì sang node 'tools', nếu không thì trả lời luôn
workflow.add_conditional_edges("assistant", tools_condition)
workflow.add_edge("tools", "assistant")

# Đóng gói và biên dịch thành Agent
agent_executor = workflow.compile()

# 5. Hàm dọn dẹp hệ thống
def cleanup():
    try:
        if 'legal_index' in globals():
            global legal_index
            del legal_index
    except:
        pass

atexit.register(cleanup)

# 6. Giao diện chạy thử nghiệm
if __name__ == "__main__":
    print(f"{Colors.BOLD}{Colors.HEADER}=== HỆ THỐNG TRỢ LÝ BẤT ĐỘNG SẢN HÀ NỘI ==={Colors.END}")
    print(f"{Colors.CYAN}Gõ 'thoát', 'quit' hoặc 'exit' để dừng chương trình.{Colors.END}\n")
    
    # Khởi tạo Lịch sử trò chuyện với System Prompt làm phần tử đầu tiên
    chat_history = [
        SystemMessage(content="Bạn là trợ lý BĐS Hà Nội chuyên nghiệp. Hãy kết hợp thông tin từ database và pháp luật để trả lời đầy đủ, chi tiết bằng tiếng Việt. Tránh in ra các định dạng thô của tool. Hãy nhớ lại các thông tin người dùng đã cung cấp ở các câu hỏi trước nếu cần thiết.")
    ]

    try:
        while True:
            # Nhập câu hỏi
            question = input(f"{Colors.BOLD}{Colors.BLUE}👤 NGƯỜI DÙNG: {Colors.END}")
            
            # Điều kiện thoát vòng lặp
            if question.lower().strip() in ['thoát', 'quit', 'exit']:
                print(f"\n{Colors.GREEN}Cảm ơn bạn đã sử dụng hệ thống. Tạm biệt!{Colors.END}")
                break
                
            if not question.strip():
                continue

            print(f"{Colors.YELLOW}🤖 AI đang suy luận và xử lý dữ liệu...{Colors.END}")
            
            # Thêm câu hỏi mới vào lịch sử
            chat_history.append(HumanMessage(content=question))
            
            # Bắt đầu bấm giờ
            start_time = time.time()
            
            # Kích hoạt Agent với toàn bộ lịch sử
            response = agent_executor.invoke({
                "messages": chat_history
            })
            
            # Kết thúc bấm giờ
            end_time = time.time()
            process_time = end_time - start_time
            
            # Cập nhật lịch sử trò chuyện mới nhất (bao gồm cả phản hồi của AI và các bước gọi Tool)
            chat_history = response["messages"]
            
            # Tìm tin nhắn cuối cùng để in ra
            final_answer = ""
            for msg in reversed(chat_history):
                if msg.type == "ai" and msg.content:
                    if isinstance(msg.content, list):
                        for part in msg.content:
                            if part.get('type') == 'text':
                                final_answer += part['text'] + "\n"
                    else:
                        final_answer = msg.content
                    break
            
            if not final_answer:
                final_answer = "Xin lỗi, tôi đã gặp khó khăn khi tổng hợp câu trả lời."

            # In kết quả
            print(f"\n{Colors.BOLD}{Colors.GREEN}🏠 TRỢ LÝ ({process_time:.2f} giây):{Colors.END}")
            print("-" * 60)
            print(final_answer.strip())
            print("-" * 60 + "\n")

    except KeyboardInterrupt:
        print(f"\n{Colors.GREEN}Đã ngắt chương trình an toàn!{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}❌ Lỗi thực thi: {e}{Colors.END}")
    finally:
        cleanup()