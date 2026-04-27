from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import appointments, auth, properties, webhooks, districts

app = FastAPI(
    title="Hanoi Real Estate API",
    description="API cho hệ thống Mua bán/Cho thuê Bất động sản tích hợp Chatbot",
    version="1.0.0"
)

# Cấu hình CORS để cho phép Frontend (Flutter Web) gọi API mà không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Trong production nên thay bằng domain thật
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn (Include) các router vào ứng dụng chính
app.include_router(auth.router)
app.include_router(properties.router)
app.include_router(appointments.router)
app.include_router(webhooks.router)
app.include_router(districts.router)

@app.get("/")
def read_root():
    return {"message": "Chào mừng đến với API Hệ thống Bất động sản Hà Nội!"}
