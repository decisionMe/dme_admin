# routes/monitoring.py

"""
Routes for subscription validation monitoring and alerting.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case
from datetime import datetime, timedelta
from database import get_db
from models.subscription_event import SubscriptionEvent, EventType, EventStatus
from models.globals import GlobalConfig
from auth import verify_session_token, SESSION_COOKIE_NAME
from fastapi import status
from fastapi.responses import RedirectResponse
import logging
import json
from typing import Dict, List, Any

logger = logging.getLogger("monitoring")

# Create router
router = APIRouter()

# Template configuration
templates = Jinja2Templates(directory="templates")

# Alert thresholds
STRIPE_API_FAILURE_THRESHOLD = 0.1  # 10% failure rate
VALIDATION_SPIKE_THRESHOLD = 2.0  # 2x normal rate
ALERT_CHECK_WINDOW_MINUTES = 15


@router.get("/admin/monitoring")
async def monitoring_dashboard(request: Request, db: Session = Depends(get_db)):
    """Display subscription monitoring dashboard"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    try:
        # Get current date range (last 7 days by default)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        
        return templates.TemplateResponse(
            "admin/monitoring.html",
            {
                "request": request,
                "is_authenticated": True,
                "start_date": start_date.date(),
                "end_date": end_date.date()
            }
        )
    except Exception as e:
        logger.error(f"Error loading monitoring dashboard: {e}")
        return templates.TemplateResponse(
            "admin/monitoring.html",
            {
                "request": request,
                "is_authenticated": True,
                "error": "Failed to load monitoring data"
            }
        )


@router.get("/api/admin/monitoring/summary")
async def get_monitoring_summary(
    request: Request,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get monitoring summary data"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get validation checks summary
        validation_stats = db.query(
            func.count(SubscriptionEvent.id).label('total'),
            func.sum(case((SubscriptionEvent.event_status == EventStatus.SUCCESS, 1), else_=0)).label('successful'),
            func.sum(case((SubscriptionEvent.event_status == EventStatus.FAILURE, 1), else_=0)).label('failed')
        ).filter(
            and_(
                SubscriptionEvent.event_type == EventType.VALIDATION_CHECK,
                SubscriptionEvent.created_at >= start_date
            )
        ).first()
        
        # Get Stripe API call stats
        stripe_stats = db.query(
            func.count(SubscriptionEvent.id).label('total'),
            func.sum(case((SubscriptionEvent.event_status == EventStatus.SUCCESS, 1), else_=0)).label('successful'),
            func.sum(case((SubscriptionEvent.event_status == EventStatus.FAILURE, 1), else_=0)).label('failed'),
            func.avg(SubscriptionEvent.response_time_ms).label('avg_response_time')
        ).filter(
            and_(
                SubscriptionEvent.event_type == EventType.STRIPE_API_CALL,
                SubscriptionEvent.created_at >= start_date
            )
        ).first()
        
        # Get redirect count
        redirect_count = db.query(func.count(SubscriptionEvent.id)).filter(
            and_(
                SubscriptionEvent.event_type == EventType.REDIRECT,
                SubscriptionEvent.created_at >= start_date
            )
        ).scalar()
        
        # Get unique users affected
        unique_users = db.query(func.count(func.distinct(SubscriptionEvent.user_id))).filter(
            and_(
                SubscriptionEvent.event_type == EventType.VALIDATION_CHECK,
                SubscriptionEvent.event_status == EventStatus.FAILURE,
                SubscriptionEvent.created_at >= start_date
            )
        ).scalar()
        
        # Calculate rates
        validation_success_rate = 0
        if validation_stats.total:
            validation_success_rate = (validation_stats.successful or 0) / validation_stats.total * 100
            
        stripe_success_rate = 0
        if stripe_stats.total:
            stripe_success_rate = (stripe_stats.successful or 0) / stripe_stats.total * 100
        
        return JSONResponse({
            "period_days": days,
            "validation": {
                "total_checks": validation_stats.total or 0,
                "successful": validation_stats.successful or 0,
                "failed": validation_stats.failed or 0,
                "success_rate": round(validation_success_rate, 2)
            },
            "stripe_api": {
                "total_calls": stripe_stats.total or 0,
                "successful": stripe_stats.successful or 0,
                "failed": stripe_stats.failed or 0,
                "success_rate": round(stripe_success_rate, 2),
                "avg_response_time_ms": round(stripe_stats.avg_response_time or 0, 2)
            },
            "redirects": {
                "total": redirect_count or 0,
                "unique_users": unique_users or 0
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting monitoring summary: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/admin/monitoring/timeline")
async def get_monitoring_timeline(
    request: Request,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get timeline data for charts"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get daily validation stats
        daily_validations = db.query(
            func.date(SubscriptionEvent.created_at).label('date'),
            func.count(SubscriptionEvent.id).label('total'),
            func.sum(case((SubscriptionEvent.event_status == EventStatus.FAILURE, 1), else_=0)).label('failed')
        ).filter(
            and_(
                SubscriptionEvent.event_type == EventType.VALIDATION_CHECK,
                SubscriptionEvent.created_at >= start_date
            )
        ).group_by(func.date(SubscriptionEvent.created_at)).all()
        
        # Get daily Stripe API stats
        daily_stripe = db.query(
            func.date(SubscriptionEvent.created_at).label('date'),
            func.count(SubscriptionEvent.id).label('total'),
            func.sum(case((SubscriptionEvent.event_status == EventStatus.FAILURE, 1), else_=0)).label('failed')
        ).filter(
            and_(
                SubscriptionEvent.event_type == EventType.STRIPE_API_CALL,
                SubscriptionEvent.created_at >= start_date
            )
        ).group_by(func.date(SubscriptionEvent.created_at)).all()
        
        # Format for charts
        validation_data = {
            "dates": [str(row.date) for row in daily_validations],
            "total": [row.total for row in daily_validations],
            "failed": [row.failed for row in daily_validations]
        }
        
        stripe_data = {
            "dates": [str(row.date) for row in daily_stripe],
            "total": [row.total for row in daily_stripe],
            "failed": [row.failed for row in daily_stripe]
        }
        
        return JSONResponse({
            "validation_timeline": validation_data,
            "stripe_timeline": stripe_data
        })
        
    except Exception as e:
        logger.error(f"Error getting monitoring timeline: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/admin/monitoring/recent-failures")
async def get_recent_failures(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get recent failure events"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    
    try:
        # Get recent failures
        failures = db.query(SubscriptionEvent).filter(
            SubscriptionEvent.event_status == EventStatus.FAILURE
        ).order_by(SubscriptionEvent.created_at.desc()).limit(limit).all()
        
        # Format for response
        failure_list = []
        for failure in failures:
            failure_list.append({
                "id": failure.id,
                "event_type": failure.event_type.value,
                "user_email": failure.user_email,
                "error_message": failure.error_message,
                "created_at": failure.created_at.isoformat(),
                "details": failure.details
            })
        
        return JSONResponse({"failures": failure_list})
        
    except Exception as e:
        logger.error(f"Error getting recent failures: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/admin/monitoring/alerts")
async def check_alerts(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check for alert conditions"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    
    try:
        alerts = []
        check_time = datetime.utcnow() - timedelta(minutes=ALERT_CHECK_WINDOW_MINUTES)
        
        # Check Stripe API failure rate
        stripe_recent = db.query(
            func.count(SubscriptionEvent.id).label('total'),
            func.sum(case((SubscriptionEvent.event_status == EventStatus.FAILURE, 1), else_=0)).label('failed')
        ).filter(
            and_(
                SubscriptionEvent.event_type == EventType.STRIPE_API_CALL,
                SubscriptionEvent.created_at >= check_time
            )
        ).first()
        
        if stripe_recent.total and stripe_recent.total > 5:  # Only alert if meaningful volume
            failure_rate = stripe_recent.failed / stripe_recent.total
            if failure_rate > STRIPE_API_FAILURE_THRESHOLD:
                alerts.append({
                    "type": "stripe_failure_rate",
                    "severity": "high",
                    "message": f"Stripe API failure rate is {failure_rate*100:.1f}% (threshold: {STRIPE_API_FAILURE_THRESHOLD*100}%)",
                    "details": {
                        "total_calls": stripe_recent.total,
                        "failed_calls": stripe_recent.failed
                    }
                })
        
        # Check for validation spike
        current_validations = db.query(func.count(SubscriptionEvent.id)).filter(
            and_(
                SubscriptionEvent.event_type == EventType.VALIDATION_CHECK,
                SubscriptionEvent.created_at >= check_time
            )
        ).scalar()
        
        # Compare to previous period
        previous_time = check_time - timedelta(minutes=ALERT_CHECK_WINDOW_MINUTES)
        previous_validations = db.query(func.count(SubscriptionEvent.id)).filter(
            and_(
                SubscriptionEvent.event_type == EventType.VALIDATION_CHECK,
                SubscriptionEvent.created_at >= previous_time,
                SubscriptionEvent.created_at < check_time
            )
        ).scalar()
        
        if previous_validations and previous_validations > 5:  # Only alert if meaningful volume
            spike_ratio = current_validations / previous_validations
            if spike_ratio > VALIDATION_SPIKE_THRESHOLD:
                alerts.append({
                    "type": "validation_spike",
                    "severity": "medium",
                    "message": f"Validation checks spiked {spike_ratio:.1f}x compared to previous period",
                    "details": {
                        "current_period": current_validations,
                        "previous_period": previous_validations
                    }
                })
        
        return JSONResponse({
            "alerts": alerts,
            "checked_at": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error checking alerts: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})