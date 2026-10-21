# backend/app/main.py
from fastapi import FastAPI
from app.router import router
from app.db.database import Base, engine
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from app.models import user_model, pooling_model, profile_model, service_model, message_model, conversation_model, campus_model  # noqa: F401
import logging
from logging.handlers import RotatingFileHandler
import os
from app.core.log_redaction import RedactSecretsFilter

load_dotenv()

# Configure logging
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

# Create formatters
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# File handler for all logs
file_handler = RotatingFileHandler(
    os.path.join(log_dir, "app.log"),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# File handler for errors only
error_handler = RotatingFileHandler(
    os.path.join(log_dir, "error.log"),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, error_handler]
)

# Also add console handler for development
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)

# httpx/httpcore log full request URLs (including ?api_key=...) at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Scrub API keys from every record written by any handler configured here.
for _handler in (file_handler, error_handler, console_handler):
    _handler.addFilter(RedactSecretsFilter())
# This function will create the database tables.
def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

# This is a "lifespan" event handler.
# The code within this "startup" event will run once, before the app starts receiving requests.
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    create_db_and_tables()
    print("Database tables created.")
    yield
    print("Shutting down...")

# Create the FastAPI app instance with the lifespan event handler
app = FastAPI(title="TripSync API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allows all headers
)
# Include the main router
app.include_router(router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "TripSync API is running!"}