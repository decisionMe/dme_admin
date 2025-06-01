# models/cms_list.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from database import Base
from sqlalchemy.orm import Session
from models.company import Company
from models.cms import CMS

class CMSList(Base):
    __tablename__ = "cms_list"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    image = Column(String, nullable=True)
    sequence = Column(Integer, nullable=True)
    content = Column(Text, nullable=True)  # Can contain HTML including links
    cms_id = Column(UUID(as_uuid=True), ForeignKey('cms.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    cms = relationship("CMS", back_populates="cms_lists")

    def get_tutorials(db: Session):
        company = db.query(Company).first()
        cms = db.query(CMS).filter_by(field_name="tutorials",company_id=company.id).first()

        if not cms:
            cms = CMS(field_name="tutorials", html_content="", company_id=company.id)

            db.add(cms)
            db.commit()

        cms_list = db.query(CMSList).filter_by(cms_id=cms.id).order_by(CMSList.sequence.asc()).all()

        return cms_list
        
