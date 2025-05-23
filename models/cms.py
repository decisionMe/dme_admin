# models/cms.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from models.company import Company
from database import Base

class CMS(Base):
    __tablename__ = "cms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    field_name = Column(String, nullable=False)
    html_content = Column(Text, nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company", back_populates="cms")
    # cms_lists = relationship("CMSList", back_populates="cms", cascade="all, delete-orphan")

    # Unique constraint for field_name and company_id combination
    __table_args__ = (
        UniqueConstraint('field_name', 'company_id', name='uix_field_name_company_id'),
        {'extend_existing': True}
    )
