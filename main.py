import os
import sqlite3
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import Signer, BadSignature

app = FastAPI(title="Ceiling Calculator")
templates = Jinja2Templates(directory="templates")

# Секретный ключ для защиты кук авторизации
SECRET_KEY = "super-secret-key-change-me-in-production"
signer = Signer(SECRET_KEY)

DB_PATH = "data/ceilings.db"

# Инициализация базы данных SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    # Таблица истории расчетов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            area REAL NOT NULL,
            material TEXT NOT NULL,
            corners INTEGER NOT NULL,
            lights INTEGER NOT NULL,
            total_price REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Функция проверки авторизации пользователя по кукам
def get_current_user(request: Request):
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None
    try:
        username = signer.unsign(session_cookie).decode("utf-8")
        return username
    except BadSignature:
        return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: str = Depends(get_current_user)):
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "user": None})
    
    # Получаем историю расчетов пользователя
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT area, material, corners, lights, total_price FROM history WHERE username = ? ORDER BY id DESC", (user,))
    history = cursor.fetchall()
    conn.close()
    
    return templates.TemplateResponse("calculator.html", {"request": request, "user": user, "history": history})

@app.post("/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip()
    if not username or not password:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Поля не могут быть пустыми"})
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        conn.close()
        return templates.TemplateResponse("login.html", {"request": request, "message": "Регистрация успешна! Теперь войдите."})
    except sqlite3.IntegrityError:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Пользователь с таким логином уже существует"})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = ?", (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0] == password:
        response = RedirectResponse(url="/", status_code=303)
        # Подписываем куку, чтобы пользователь не мог её подделать
        signed_cookie = signer.sign(username.strip().encode("utf-8"))
        response.set_cookie(key="session", value=signed_cookie.decode("utf-8"), httponly=True)
        return response
    
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверное имя пользователя или пароль"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session")
    return response

@app.post("/calculate")
async def calculate(
    request: Request,
    area: float = Form(...),
    material: str = Form(...),
    corners: int = Form(...),
    lights: int = Form(...),
    user: str = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    # Логика прайс-листа
    prices = {"матовый": 300, "глянцевый": 350, "тканевый": 600}
    material_price = prices.get(material, 300)
    
    # Расчёт стоимости
    base_cost = area * material_price
    
    # Первые 4 угла бесплатно, каждый доп. угол +100 руб
    extra_corners = max(0, corners - 4)
    corners_cost = extra_corners * 100
    
    # Свет: 250 руб за штуку
    lights_cost = lights * 250
    
    total_price = base_cost + corners_cost + lights_cost
    
    # Сохраняем результат в историю
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO history (username, area, material, corners, lights, total_price) VALUES (?, ?, ?, ?, ?, ?)",
        (user, area, material, corners, lights, total_price)
    )
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/", status_code=303)
