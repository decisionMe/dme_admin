import os
from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Local imports
from database import get_db
from models.prompt import Prompt
from auth import ADMIN_PASSWORD, verify_admin, login_required, create_session_token, SESSION_COOKIE_NAME, verify_session_token

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("dme_admin")

# Create FastAPI app
app = FastAPI(title="DME Admin")

# Template configuration
templates = Jinja2Templates(directory="templates")

# Data models for request validation
class PromptUpdate(BaseModel):
    name: str
    notes: str
    prompt: str

# Log that we have the password but don't log the actual value
logger.info("Admin password loaded from environment")

# Define routes
@app.get("/")
async def root(request: Request):
    """Root route - redirects to prompts page if authenticated, otherwise to login page"""
    # Check if user is logged in
    is_authenticated = login_required(request)
    if is_authenticated:
        return RedirectResponse(url="/prompts", status_code=status.HTTP_302_FOUND)
    else:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/login")
async def login_page(request: Request, error: Optional[str] = None):
    """Login page"""
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error}
    )

@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    """Process login form"""
    if password == ADMIN_PASSWORD:
        # Create session token
        session_token = create_session_token()
        
        # Redirect to prompts page with session cookie
        response = RedirectResponse(url="/prompts", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            httponly=True,
            secure=False,  # Set to True for production with HTTPS
            samesite="lax",
            max_age=3600 * 8 # 8 hours
        )
        return response
    else:
        # Return to login page with error
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Invalid password"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

@app.get("/logout")
async def logout():
    """Logout - clear session cookie"""
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response

@app.get("/prompts")
async def list_prompts(
    request: Request, 
    db: Session = Depends(get_db)
):
    """Display all prompts"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        
    try:
        prompts = db.query(Prompt).order_by(Prompt.name).all()
        return templates.TemplateResponse(
            "prompts.html", 
            {"request": request, "prompts": prompts, "is_authenticated": True}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")
        return templates.TemplateResponse(
            "prompts.html", 
            {
                "request": request, 
                "prompts": [], 
                "is_authenticated": True,
                "error": "Failed to load prompts from database"
            }
        )

@app.post("/prompts/create")
async def create_prompt(
    request: Request,
    name: str = Form(...),
    notes: str = Form(""),
    prompt: str = Form(...),
    db: Session = Depends(get_db)
):
    """Create a new prompt"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    try:
        # Process line breaks for storage
        notes = (notes
                .replace('\r\n', '\n')
                .replace('\n\n', '<br><br>')
                .replace('\n', '<br>'))
                
        prompt_text = (prompt
                    .replace('\r\n', '\n')
                    .replace('\n\n', '<br><br>')
                    .replace('\n', '<br>'))
        
        # Create new prompt object
        new_prompt = Prompt(
            name=name,
            notes=notes,
            prompt=prompt_text
        )
        
        # Add to database
        db.add(new_prompt)
        db.commit()
        
        # Redirect to prompts page
        return RedirectResponse(url="/prompts", status_code=status.HTTP_302_FOUND)
    except SQLAlchemyError as e:
        logger.error(f"Database error creating prompt: {str(e)}")
        db.rollback()
        
        # Return to form with error
        prompts = db.query(Prompt).order_by(Prompt.name).all()
        return templates.TemplateResponse(
            "prompts.html", 
            {
                "request": request, 
                "prompts": prompts, 
                "is_authenticated": True,
                "error": f"Failed to create prompt: {str(e)}"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.put("/prompts/{prompt_id}")
async def update_prompt(
    request: Request,
    prompt_id: int,
    prompt_data: PromptUpdate,
    db: Session = Depends(get_db)
):
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    """Update an existing prompt"""
    try:
        # Get the prompt
        prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        # Update name
        prompt.name = prompt_data.name
        
        # Handle double line breaks and format for database
        prompt.notes = (prompt_data.notes
                      .replace('\r\n', '\n')
                      .replace('\n\n', '<br><br>')
                      .replace('\n', '<br>'))

        prompt.prompt = (prompt_data.prompt
                       .replace('\r\n', '\n')
                       .replace('\n\n', '<br><br>')
                       .replace('\n', '<br>'))
        
        # Save changes
        db.commit()
        return {"success": True}
    except SQLAlchemyError as e:
        logger.error(f"Database error updating prompt {prompt_id}: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Run the application
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
