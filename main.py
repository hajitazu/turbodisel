from fastapi import FastAPI, Request, Form, UploadFile, File, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer
from passlib.hash import bcrypt
import json, os, shutil
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

USER_DB = "users.json"
CHAT_DB = "chat_history.json"
CONTACT_DB = "contacts.json"
SECRET = "chat_secret_key"
serializer = URLSafeSerializer(SECRET)

# Helper functions
def load_json(file):
    if not os.path.exists(file):
        return {} if "users" in file or "contacts" in file else []
    with open(file) as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# Auth
def get_current_user(request: Request):
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    try:
        user_id = serializer.loads(cookie)
        users = load_json(USER_DB)
        if str(user_id) in users:
            return {"id": str(user_id), "name": users[str(user_id)]["name"]}
    except:
        return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return RedirectResponse("/chat")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(response: Response, id: str = Form(...), password: str = Form(...)):
    users = load_json(USER_DB)
    if id not in users or not bcrypt.verify(password, users[id]["password"]):
        return RedirectResponse("/login", status_code=302)
    session = serializer.dumps(id)
    response = RedirectResponse("/chat", status_code=302)
    response.set_cookie("session", session, httponly=True, max_age=60*60*24*7)
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(id: str = Form(...), name: str = Form(...), password: str = Form(...)):
    users = load_json(USER_DB)
    if not id.isdigit() or not (1 <= int(id) <= 300) or id in users:
        return RedirectResponse("/register", status_code=302)
    users[id] = {"name": name, "password": bcrypt.hash(password)}
    save_json(USER_DB, users)
    return RedirectResponse("/login", status_code=302)

@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("chat.html", {"request": request, "user": user})

@app.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    user = get_current_user(request)
    if not user:
        return {"error": "Unauthorized"}
    if file.filename:
        file_path = os.path.join("uploads", file.filename)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"url": f"/uploads/{file.filename}"}
    return {"error": "No file"}

# WebSocket realtime
connections = {}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            from_id = user_id
            to_id = data["to"]
            message = {
                "from": from_id,
                "to": to_id,
                "content": data["content"],
                "timestamp": datetime.now().isoformat(),
                "status": "sent"
            }
            chat_history = load_json(CHAT_DB)
            chat_history.append(message)
            save_json(CHAT_DB, chat_history)
            # Send to recipient if online
            if to_id in connections:
                await connections[to_id].send_json(message)
    except WebSocketDisconnect:
        del connections[user_id]
