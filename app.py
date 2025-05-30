# app.py
import os
from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models.cms import CMS
from models.tree_node import TreeNode
from models.company import Company
import logging
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv
import sys
import stripe

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
numeric_level = getattr(logging, log_level, None)
if not isinstance(numeric_level, int):
    print(f"Invalid log level: {log_level}, defaulting to INFO")
    numeric_level = logging.INFO

logging.basicConfig(
    level=numeric_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.getenv("LOG_FILE", "app.log"))
    ]
)
logger = logging.getLogger("dme_admin")

# Local imports
from database import get_db, Base, engine
from models.prompt import Prompt
from models.subscription_user import SubscriptionUser
from auth import ADMIN_PASSWORD, verify_admin, login_required, create_session_token, SESSION_COOKIE_NAME, verify_session_token
from middleware import RawBodyMiddleware

# Import routes
from routes.subscription import router as subscription_router
from routes.admin_subscription import router as admin_subscription_router
from routes.monitoring import router as monitoring_router

# Create debug directory if enabled
if os.getenv("SAVE_WEBHOOK_BODIES", "false").lower() == "true" or \
   os.getenv("SAVE_WEBHOOK_DIAGNOSTICS", "false").lower() == "true":
    debug_dir = os.getenv("DEBUG_DIR", "debug_logs")
    os.makedirs(debug_dir, exist_ok=True)
    logger.info(f"Debug directory created: {debug_dir}")

# Create database tables if they don't exist
Base.metadata.create_all(bind=engine)
logger.info("Database tables created if they didn't exist")

# Create FastAPI app
app = FastAPI(title="DME Admin")

# Add raw body middleware for Stripe webhooks - this must come before any other middleware
app.add_middleware(RawBodyMiddleware)
logger.info("RawBodyMiddleware added for Stripe webhooks")

# Include subscription router
app.include_router(subscription_router)
logger.info("Subscription router included")

# Include admin subscription router
app.include_router(admin_subscription_router)
logger.info("Admin subscription router included")

# Include monitoring router
app.include_router(monitoring_router)
logger.info("Monitoring router included")

# Template configuration
templates = Jinja2Templates(directory="templates")

# Data models for request validation
class PromptUpdate(BaseModel):
    name: str
    notes: str
    prompt: str

# Log that we have the password but don't log the actual value
logger.info("Admin password loaded from environment")

# Define placeholder routes for testing
@app.get("/dashboard")
async def dashboard_placeholder():
    """Placeholder dashboard for testing subscription flow"""
    return JSONResponse(content={
        "message": "Subscription completed successfully!",
        "status": "You are now subscribed.",
        "next_steps": "This is a placeholder dashboard page for testing."
    })

@app.get("/gift-confirmation")
async def gift_confirmation_placeholder():
    """Placeholder gift confirmation page for testing subscription flow"""
    return JSONResponse(content={
        "message": "Gift subscription sent!",
        "status": "The recipient will receive an invitation email.",
        "next_steps": "This is a placeholder gift confirmation page for testing."
    })

@app.get("/error")
async def error_placeholder(reason: str = None):
    """Placeholder error page for testing subscription flow"""
    return JSONResponse(
        status_code=400,
        content={
            "message": "An error occurred during the subscription process.",
            "reason": reason or "Unknown error",
            "next_steps": "This is a placeholder error page for testing."
        }
    )

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

@app.get("/cms/about")
async def cms(request: Request, db: Session = Depends(get_db)):
    """Display the About page"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    company = db.query(Company).first()

    if not company:
        company = Company(id=1,name="DecisionMe")
        db.add(company)
        db.commit()

    about = db.query(CMS).filter_by(field_name="about",company_id=company.id).first()

    if not about:
        about = CMS(field_name="about", html_content="", company_id=company.id)
        db.add(about)
        db.commit()

    return templates.TemplateResponse(
        "about.html",
        {"request": request, "is_authenticated": True, "cms_page": "about", "about_content": about.html_content}
    )

@app.post("/cms/about/update")
async def cms_update_about(request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    try:
        company = db.query(Company).first()

        if not company:
            company = Company(id=1,name="DecisionMe")
            db.add(company)
            db.commit()

        about = db.query(CMS).filter_by(field_name="about",company_id=company.id).first()

        if about:
            about.html_content = content
        else:
            about = CMS(field_name="about", html_content=content, company_id=company.id)

        db.add(about)
        db.commit()

        return templates.TemplateResponse(
            "components/success_message.html",
            {"request": request, "message": "Content has been updated!"}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")

        return templates.TemplateResponse(
            "components/error_message.html",
            {"request": request, "message": "Failed to update content."}
        )

@app.get("/cms/help-center")
async def cms_help_center(request: Request, db: Session = Depends(get_db)):
    """Display the Help Center page"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    nodes = TreeNode.get_nodes(db)

    return templates.TemplateResponse(
        "help-center.html",
        {
            "request": request,
            "is_authenticated": True,
            "cms_page": "help-center",
            "nodes": nodes
        }
    )

@app.get("/cms/help-center/add")
async def cms_help_center_add(request: Request, db: Session = Depends(get_db)):
    """Display the Help Center add node page"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    nodes = TreeNode.get_nodes(db)

    return templates.TemplateResponse(
        "help-center-add.html",
        {
            "request": request,
            "is_authenticated": True,
            "cms_page": "help-center",
            "nodes": nodes
        }
    )

@app.get("/cms/help-center/edit/{node_id}")
async def cms_help_center_edit(request: Request, node_id: int, db: Session = Depends(get_db)):
    """Display the Help Center edit node page"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    node = TreeNode.get_node_by_id(node_id, db)

    if not node:
        return RedirectResponse(url="/cms/help-center", status_code=status.HTTP_302_FOUND)

    nodes = TreeNode.get_nodes(db, node.id)

    return templates.TemplateResponse(
        "help-center-edit.html",
        {
            "request": request,
            "is_authenticated": True,
            "cms_page": "help-center",
            "node": node,
            "nodes": nodes
        }
    )

@app.post("/cms/help-center/create")
async def cms_create_help_center_node(request: Request, title: str = Form(...), parent_id: int = Form(None), node_type: str = Form(...), html_content: str = Form(None), external_url: str = Form(None), db: Session = Depends(get_db)):
    try:
        parent_id = None if parent_id == 0 else parent_id

        node = TreeNode(
            title=title,
            parent_id=parent_id,
            is_document=node_type=="document",
            is_url=node_type=="url",
            html_content=html_content,
            external_url=external_url
        )

        db.add(node)
        db.commit()

        return templates.TemplateResponse(
            "components/help_center_table.html",
            {"request": request, "nodes": TreeNode.get_nodes(db)}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")

        return templates.TemplateResponse(
            "components/error_message.html",
            {"request": request, "message": "Failed to create node."}
        )

@app.post("/cms/help-center/update/{node_id}")
async def cms_update_help_center_node(request: Request, node_id: int, title: str = Form(...), parent_id: int = Form(None), node_type: str = Form(...), html_content: str = Form(None), external_url: str = Form(None), db: Session = Depends(get_db)):
    try:
        node = TreeNode.get_node_by_id(node_id, db)

        if not node:
            return RedirectResponse(url="/cms/help-center", status_code=status.HTTP_302_FOUND)

        node.title = title
        node.parent_id = None if parent_id == 0 else parent_id
        node.is_document = node_type=="document"
        node.is_url = node_type=="url"
        node.html_content = html_content
        node.external_url = external_url

        db.add(node)
        db.commit()

        return templates.TemplateResponse(
            "components/help_center_table.html",
            {"request": request, "nodes": TreeNode.get_nodes(db)}
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")

        return templates.TemplateResponse(
            "components/error_message.html",
            {"request": request, "message": "Failed to update node."}
        )

@app.delete("/cms/help-center/delete/{node_id}")
async def delete_node(node_id: int, request: Request, db: Session = Depends(get_db)):
    node = db.query(TreeNode).filter(TreeNode.id == node_id).first()

    logger.info("Deleting node" + str(node_id))

    if not node:
        return {"error": "Not found"}

    db.delete(node)
    db.commit()

    return templates.TemplateResponse(
        "components/help_center_table.html",
        {"request": request, "nodes": TreeNode.get_nodes(db)}
    )

@app.get("/cms/tutorials")
async def cms_tutorials(request: Request, db: Session = Depends(get_db)):
    """Display the Tutorials page"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        "tutorials.html",
        {"request": request, "is_authenticated": True, "cms_page": "tutorials"}
    )

@app.get("/subscription/recovery")
async def subscription_recovery_page(request: Request, db: Session = Depends(get_db)):
    """Admin page for subscription recovery"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    try:
        # Get recent subscription users for display
        subscription_users = db.query(SubscriptionUser).order_by(SubscriptionUser.created_at.desc()).limit(20).all()

        return templates.TemplateResponse(
            "subscription_recovery.html",
            {
                "request": request,
                "subscription_users": subscription_users,
                "is_authenticated": True
            }
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")
        return templates.TemplateResponse(
            "subscription_recovery.html",
            {
                "request": request,
                "subscription_users": [],
                "is_authenticated": True,
                "error": "Failed to load subscription users from database"
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
    """Update an existing prompt"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

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

# Subscription Required/Expired Page
@app.get("/subscription-required")
@app.get("/subscription-expired")
async def subscription_required(request: Request):
    """Default page shown when subscription is required or expired"""
    # Get support email from environment or use default
    support_email = os.getenv("SUPPORT_EMAIL", "support@decisionme.ai")

    # Get subscription URL from environment or use default
    subscription_url = os.getenv("SUBSCRIPTION_URL", "/subscribe")

    return templates.TemplateResponse(
        "subscription_required.html",
        {
            "request": request,
            "support_email": support_email,
            "subscription_url": subscription_url
        }
    )

# Diagnostic endpoint for webhook testing
@app.get("/webhook-config")
async def webhook_config():
    """Returns the current webhook configuration (safe information only)"""
    return {
        "webhook_endpoint": f"{os.getenv('APP_URL', 'http://localhost:8001')}/subscription/stripe/webhook",
        "stripe_api_configured": bool(os.getenv("STRIPE_API_KEY")),
        "webhook_secret_configured": bool(os.getenv("STRIPE_WEBHOOK_SECRET")),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "debug_enabled": os.getenv("SAVE_WEBHOOK_BODIES", "false").lower() == "true",
        "debug_signatures": os.getenv("DEBUG_SIGNATURES", "false").lower() == "true"
    }

@app.post("/create-checkout-session")
async def create_checkout_session():
    """Create a new checkout session for testing"""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'DAR Pro I',
                    },
                    'unit_amount': 3000,  # $30.00
                    'recurring': {
                        'interval': 'year'
                    }
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url=os.getenv("APP_URL", "http://localhost:8001") + "/subscription/stripe/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=os.getenv("APP_URL", "http://localhost:8001") + "/error?reason=checkout_cancelled",
        )
        return {"id": session.id}
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test-checkout")
async def test_checkout():
    """Serve the checkout test page"""
    with open("checkout_test.html", "r") as f:
        content = f.read()
    return HTMLResponse(content)

# Run the application
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
