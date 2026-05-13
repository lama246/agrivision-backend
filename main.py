from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from mail_config import conf
import tensorflow as tf
import numpy as np
import uuid
from PIL import Image
from jose import jwt
from datetime import datetime, timedelta
import resend
from database import engine, SessionLocal
from models import User
from database import Base
from sqlalchemy.orm import Session
from passlib.context import CryptContext



resend.api_key = "re_B29xB4Pa_8eKzrDBibBCXpkKS7ZLx7cXd"

SECRET_KEY = "supersecretkey"

ALGORITHM = "HS256"

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

Base.metadata.create_all(bind=engine)

app = FastAPI()

# Enable frontend-backend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "https://your-frontend-url.com"
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load trained model
model = tf.keras.models.load_model("plant_disease_model.keras")

# Class labels
class_names = [
    "Pepper Bell Bacterial Spot",
    "Pepper Bell Healthy",
    "Potato Early Blight",
    "Potato Late Blight",
    "Potato Healthy",
    "Tomato Bacterial Spot",
    "Tomato Early Blight",
    "Tomato Late Blight",
    "Tomato Leaf Mold",
    "Tomato Septoria Leaf Spot",
    "Tomato Spider Mites",
    "Tomato Target Spot",
    "Tomato Yellow Leaf Curl Virus",
    "Tomato Mosaic Virus",
    "Tomato Healthy"
]

def send_verification_email(user_email, token):

    verification_link = f"http://127.0.0.1:8000/verify/{token}"

    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": user_email,
        "subject": "AgriVision AI Verification",
        "html": f"""
        <h1>Welcome to AgriVision AI</h1>

        <p>Click below to verify your account:</p>

        <a href="{verification_link}">
            Verify Account
        </a>
        """
    })
# Image preprocessing
def preprocess_image(image):

    image = image.resize((224, 224))

    image_array = np.array(image) / 255.0

    image_array = np.expand_dims(image_array, axis=0)

    return image_array

from fastapi import HTTPException

def create_verification_token(email: str):

    expire = datetime.utcnow() + timedelta(hours=1)

    data = {
        "sub": email,
        "exp": expire
    }

    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)
# SIGNUP
@app.post("/signup")
async def signup(email: str = Form(...), password: str = Form(...)):

    db = SessionLocal()

    existing_user = db.query(User).filter(User.email == email).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    hashed_password = pwd_context.hash(password)

    token = str(uuid.uuid4())


    new_user = User(
        email=email,
        password=hashed_password,
        is_verified=False,
        verification_token=token
    )

    db.add(new_user)
    db.commit()

    send_verification_email(email, token)

    return {
        "message": "Verification email sent"
    }
@app.post("/reset-password")

def reset_password(
    email: str = Form(...),
    new_password: str = Form(...)
):

    db = SessionLocal()

    user = db.query(User).filter(User.email == email).first()

    if not user:

        raise HTTPException(
            status_code=404,
            detail="Email not found"
        )

    hashed_password = pwd_context.hash(new_password)

    user.password = hashed_password

    db.commit()

    return {
        "message": "Password updated successfully"
    }
@app.get("/verify/{token}")
async def verify_account(token: str):

    db = SessionLocal()

    user = db.query(User).filter(
        User.verification_token == token
    ).first()

    if not user:

        return {
            "message": "Invalid verification link"
        }

    user.is_verified = True

    user.verification_token = None

    db.commit()

    return {
        "message": "Account verified successfully"
    }
@app.get("/verify-email/{token}")
async def verify_email(token: str):

    db = SessionLocal()

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        email = payload.get("sub")

        user = db.query(User).filter(User.email == email).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.verified = True

        db.commit()

        return {
            "message": "Email verified successfully"
        }

    except:
        raise HTTPException(status_code=400, detail="Invalid or expired token")


# LOGIN
@app.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...)
):

    db = SessionLocal()

    user = db.query(User).filter(
        User.email == email
    ).first()

    # USER DOES NOT EXIST
    if not user:

        raise HTTPException(
            status_code=400,
            detail="Email not registered"
        )

    # PASSWORD WRONG
    if not pwd_context.verify(password, user.password):

        raise HTTPException(
            status_code=400,
            detail="Invalid password"
        )

    # EMAIL NOT VERIFIED
    if not user.is_verified:

        raise HTTPException(
            status_code=400,
            detail="Please verify your email first"
        )

    return {
        "message": "Login successful"
    }
@app.post("/predict")
async def predict(file: UploadFile = File(...),symptoms: str = Form(...)):

    image = Image.open(file.file).convert("RGB")

    processed_image = preprocess_image(image)

    prediction = model.predict(processed_image)

    predicted_index = np.argmax(prediction)

    confidence = float(np.max(prediction))

    disease = class_names[predicted_index]

    # WEATHER API
    import requests

    API_KEY = "310864c5a2f1db30fffea0b380dd73ce"

    city = "Kochi"

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"

    response = requests.get(url)
    if response.status_code != 200:
        temperature = 0
        humidity = 0
        condition = "Unknown"
    else:

        data = response.json()

        temperature = data["main"]["temp"]

        humidity = data["main"]["humidity"]

        condition = data["weather"][0]["main"]

    # ENVIRONMENT ALERT SYSTEM

    environment_alert = "NORMAL"

    environment_instruction = "Environmental conditions are stable."

    # HIGH HUMIDITY
    if humidity > 85:

        environment_alert = "HIGH HUMIDITY ALERT"

        environment_instruction = (
            "High humidity detected. Increased risk of fungal and bacterial disease spread. "
            "Reduce excessive watering and improve air circulation."
        )

    # VERY HIGH TEMPERATURE
    if temperature > 35:

        environment_alert = "HIGH TEMPERATURE ALERT"

        environment_instruction = (
            "Extreme temperature detected. Crops may experience heat stress. "
            "Increase irrigation during early morning and avoid afternoon watering."
        )

    # RAIN CONDITIONS
    if condition == "Rain":

        environment_alert = "RAIN ALERT"

        environment_instruction = (
            "Rainy conditions detected. Leaf wetness may accelerate disease spread. "
            "Monitor crops closely for blight and fungal infections."
        )

    # CRITICAL COMBINATION
    if humidity > 85 and condition == "Rain":

        environment_alert = "CRITICAL DISEASE SPREAD ALERT"

        environment_instruction = (
            "Critical environmental conditions detected for rapid disease transmission. "
            "Immediate field monitoring and preventive treatment recommended."
        )

        # RISK CLASSIFICATION

    risk = "LOW"

    # PEPPER
    if disease == "Pepper Bell Bacterial Spot":

            if humidity > 80:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

    elif disease == "Pepper Bell Healthy":
            risk = "LOW"


        # POTATO
    elif disease == "Potato Early Blight":

            if humidity > 75:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

    elif disease == "Potato Late Blight":

            if humidity > 80 or condition == "Rain":
                risk = "CRITICAL"
            else:
                risk = "HIGH"

    elif disease == "Potato Healthy":
            risk = "LOW"


        # TOMATO
    elif disease == "Tomato Bacterial Spot":

            if humidity > 80:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

    elif disease == "Tomato Early Blight":

            if humidity > 75:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

    elif disease == "Tomato Late Blight":

            if humidity > 80 or condition == "Rain":
                risk = "CRITICAL"
            else:
                risk = "HIGH"

    elif disease == "Tomato Leaf Mold":

            if humidity > 85:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

    elif disease == "Tomato Septoria Leaf Spot":

            if humidity > 80:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

    elif disease == "Tomato Spider Mites":

            if temperature > 30:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

    elif disease == "Tomato Target Spot":

            if humidity > 75:
                risk = "HIGH"
            else:
                risk = "MEDIUM"

    elif disease == "Tomato Yellow Leaf Curl Virus":
            risk = "CRITICAL"

    elif disease == "Tomato Mosaic Virus":
            risk = "CRITICAL"

    elif disease == "Tomato Healthy":
            risk = "LOW"

    treatment = "No treatment required."
    if disease == "Pepper Bell Bacterial Spot":

            treatment = (
                "Apply copper-based bactericide. "
                "Remove infected leaves and avoid overhead watering."
            )
    elif disease == "Potato Early Blight":

            treatment = (
            "Apply fungicide and remove infected leaves. "
            "Improve air circulation."
        )

    elif disease == "Potato Late Blight":

            treatment = (
                "Immediate fungicide treatment required. "
                "Avoid excess moisture and isolate infected plants."
            )
    elif disease == "Tomato Early Blight":

            treatment = (
                "Use fungicide spray and prune affected leaves."
            )

    elif disease == "Tomato Late Blight":

            treatment = (
                "Urgent fungicide treatment required. "
                "Reduce watering and monitor nearby plants."
            )

    elif disease == "Tomato Leaf Mold":

            treatment = (
                "Reduce humidity and improve greenhouse ventilation."
            )

    elif disease == "Tomato Spider Mites":

            treatment = (
                "Use neem oil or miticide spray. "
                "Increase humidity slightly."
            )

    elif disease == "Tomato Yellow Leaf Curl Virus":

            treatment = (
                "Remove infected plants immediately. "
                "Control whitefly population."
            )

    elif disease == "Tomato Mosaic Virus":

            treatment = (
                "Remove infected plants and disinfect tools."
            )
    elif "Healthy" in disease:

            treatment = (
            "Crop is healthy. Continue regular monitoring and irrigation."
        )

    
    symptom_vector = vectorizer.transform([symptoms])

    symptom_prediction = nlp_model.predict(symptom_vector)[0]

    # AI AGENT DECISIONS

    urgency = "LOW"

    immediate_treatment = "NO"

    reduce_watering = "NO"

    monitoring_alert = "NO"

    weather_recheck = "NO"


    # CRITICAL CONDITIONS
    if risk == "CRITICAL":

        urgency = "HIGH"

        immediate_treatment = "YES"

        reduce_watering = "YES"

        monitoring_alert = "YES"

        weather_recheck = "YES"


    # HIGH RISK CONDITIONS
    elif risk == "HIGH":

        urgency = "HIGH"

        immediate_treatment = "YES"

        monitoring_alert = "YES"

        weather_recheck = "YES"

        if humidity > 80:
            reduce_watering = "YES"


    # MEDIUM RISK CONDITIONS
    elif risk == "MEDIUM":

        urgency = "MEDIUM"

        monitoring_alert = "YES"

        weather_recheck = "YES"


    # LOW RISK CONDITIONS
    elif risk == "LOW":

        urgency = "LOW"

    return {
        "disease": disease,
        "confidence": f"{confidence * 100:.2f}%",
        "temperature": temperature,
        "humidity": humidity,
        "weather": condition,
        "risk":risk,
        "symptom_analysis": symptom_prediction,
        "urgency": urgency,
        "immediate_treatment": immediate_treatment,
        "reduce_watering": reduce_watering,
        "monitoring_alert": monitoring_alert,
        "environment_alert": environment_alert,
        "environment_instruction": environment_instruction,
        "treatment": treatment

    }
import joblib

nlp_model = joblib.load("nlp_model.pkl")

vectorizer = joblib.load("vectorizer.pkl")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)