import os
import shutil
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from dotenv import load_dotenv

load_dotenv()

# --- Email Config ---
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

def send_status_email(to_email: str, claim_id: int, full_name: str, new_status: str):
    if not to_email or not SMTP_USER:
        print(f"Skipping email to {to_email} (No SMTP config or email provided)")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = f"STAR ASSURANCES <{SMTP_USER}>"
        msg['To'] = to_email
        msg['Subject'] = f"Mise à jour de votre déclaration STAR #{claim_id}"

        status_text = "en cours de révision" if new_status == "reviewed" else "clôturé"
        
        body = f"""
        Bonjour {full_name},
        
        Nous vous informons que l'état de votre déclaration d'accident #{claim_id} a été mis à jour.
        
        Nouvel état : {status_text.upper()}
        
        Merci de votre confiance,
        L'équipe STAR ASSURANCES Tunisie.
        """
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

# --- Database Setup ---
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://user:userpassword@db:3306/insurance_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Models ---
class Claim(Base):
    __tablename__ = "claims"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255))
    email = Column(String(255), nullable=True)
    cin = Column(String(50))
    policy_number = Column(String(100))
    phone_number = Column(String(20))
    vehicle_details = Column(Text)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    attachments = relationship("Attachment", back_populates="claim")

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"))
    file_name = Column(String(255))
    file_path = Column(String(255))
    file_type = Column(String(50))
    claim = relationship("Claim", back_populates="attachments")

def init_db():
    retries = 10
    while retries > 0:
        try:
            print(f"Connecting to database at {DATABASE_URL}...")
            Base.metadata.create_all(bind=engine)
            
            # Simple migration hack for existing DB
            with engine.connect() as conn:
                # Add email column if not exists
                try:
                    conn.execute(text("ALTER TABLE claims ADD COLUMN email VARCHAR(255) NULL AFTER full_name"))
                    conn.commit()
                    print("Database migrated: added email column")
                except Exception:
                    pass
                
                # Drop accident_description column if exists
                try:
                    conn.execute(text("ALTER TABLE claims DROP COLUMN accident_description"))
                    conn.commit()
                    print("Database migrated: removed accident_description column")
                except Exception:
                    pass

            print("Database connected and tables verified!")
            return
        except Exception as e:
            print(f"Database connection failed: {e}. Retrying in 5 seconds...")
            retries -= 1
            time.sleep(5)
    raise Exception("Could not connect to database after multiple retries")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

# --- FastAPI App ---
app = FastAPI(title="Insurance Accident Declaration API", lifespan=lifespan)

# Serve uploaded files
if not os.path.exists("uploads"):
    os.makedirs("uploads")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://insurance.local", "http://frontend.local"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static Car Data ---
CAR_MODELS = {
    "Peugeot": ["208", "308", "2008", "3008", "5008", "Partner"],
    "Renault": ["Clio", "Megane", "Captur", "Kadjar", "Symbol", "Kangoo"],
    "Volkswagen": ["Golf", "Polo", "Passat", "Tiguan", "Caddy"],
    "Citroen": ["C3", "C4", "C5", "Berlingo"],
    "Dacia": ["Sandero", "Duster", "Logan"],
    "Fiat": ["500", "Panda", "Tipo", "Fiorino"],
    "Toyota": ["Yaris", "Corolla", "Hilux"],
    "Hyundai": ["i10", "i20", "Tucson"],
    "Kia": ["Rio", "Picanto", "Sportage"],
    "BMW": ["Série 1", "Série 3", "Série 5", "X1", "X3", "X5"],
    "Mercedes-Benz": ["Classe A", "Classe C", "Classe E", "GLA", "GLC"],
}

@app.get("/api/car-models")
async def get_car_models():
    return CAR_MODELS

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Routes ---

@app.post("/api/claims")
async def create_claim(
    full_name: str = Form(...),
    cin: str = Form(...),
    policy_number: str = Form(...),
    phone_number: str = Form(...),
    vehicle_details: str = Form(...),
    email: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    db_claim = Claim(
        full_name=full_name,
        email=email,
        cin=cin,
        policy_number=policy_number,
        phone_number=phone_number,
        vehicle_details=vehicle_details
    )
    db.add(db_claim)
    db.commit()
    db.refresh(db_claim)

    upload_dir = "uploads"
    for file in files:
        unique_filename = f"{db_claim.id}_{datetime.now().timestamp()}_{file.filename}"
        file_path = os.path.join(upload_dir, unique_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        db_attachment = Attachment(
            claim_id=db_claim.id,
            file_name=file.filename,
            file_path=file_path,
            file_type=file.content_type
        )
        db.add(db_attachment)
    db.commit()
    return {"message": "Claim submitted successfully", "claim_id": db_claim.id}

@app.get("/api/claims")
async def get_claims(db: Session = Depends(get_db)):
    claims = db.query(Claim).all()
    result = []
    for claim in claims:
        attachments = [{"id": a.id, "file_name": a.file_name, "file_path": a.file_path} for a in claim.attachments]
        result.append({
            "id": claim.id,
            "full_name": claim.full_name,
            "email": claim.email,
            "cin": claim.cin,
            "policy_number": claim.policy_number,
            "phone_number": claim.phone_number,
            "vehicle_details": claim.vehicle_details,
            "status": claim.status,
            "created_at": claim.created_at,
            "attachments": attachments
        })
    return result

@app.patch("/api/claims/{claim_id}/status")
async def update_claim_status(claim_id: int, status: str, db: Session = Depends(get_db)):
    db_claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not db_claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    
    old_status = db_claim.status
    db_claim.status = status
    db.commit()

    # Send email if status changed and email exists
    if old_status != status and db_claim.email:
        send_status_email(db_claim.email, db_claim.id, db_claim.full_name, status)

    return {"message": "Status updated successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
