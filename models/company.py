# models/company.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    address = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)
    country = Column(String)
    website = Column(String)
    industry = Column(String)
    size = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    # teams = relationship("Team", back_populates="company", cascade="all, delete-orphan")
    cms = relationship("CMS", back_populates="company", cascade="all, delete-orphan")
    # company_admins = relationship("CompanyAdmin", back_populates="company", cascade="all, delete-orphan")
    # subscriptions = relationship("Subscription", 
    #                            back_populates="company", 
    #                            primaryjoin="Company.id==Subscription.company_id",
    #                            cascade="all, delete-orphan")
    # company_subscriptions = relationship("CompanySubscription", back_populates="company", cascade="all, delete-orphan")
