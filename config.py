from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    STRIPE_API_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    AUTH0_DOMAIN: str
    AUTH0_CLIENT_ID: str
    AUTH0_CLIENT_SECRET: str
    AUTH0_DB_CONNECTION_ID: str
    REDIRECT_URI: str
    APP_URL: str
    
    # Magic Link Configuration
    MAGIC_LINK_SECRET: str
    CLIENT_APP_URL: str
    
    class Config:
        env_file = ".env"

settings = Settings()