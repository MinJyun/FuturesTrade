import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_KEY = os.getenv("API_KEY")
    SECRET_KEY = os.getenv("SECRET_KEY")
    CA_CERT_PATH = os.getenv("CA_CERT_PATH")
    CA_PASSWORD = os.getenv("CA_PASSWORD")

    @classmethod
    def validate(cls, simulation: bool = True):
        if not cls.API_KEY or not cls.SECRET_KEY:
            raise ValueError("API_KEY and SECRET_KEY must be set in environment variables.")
        
        if not simulation:
            if not cls.CA_CERT_PATH or not cls.CA_PASSWORD:
                raise ValueError("CA_CERT_PATH and CA_PASSWORD are required for non-simulation mode.")
