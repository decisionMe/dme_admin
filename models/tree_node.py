# models/tree_node.py
# models/cms.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from py_db.db import Base

class TreeNode(Base):
    __tablename__ = "tree_nodes"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    is_expanded = Column(Boolean, default=False)
    is_document = Column(Boolean, default=False)
    is_url = Column(Boolean, default=False)
    external_url = Column(String(2048), nullable=True)
    html_content = Column(Text, nullable=True)

    # Self-referential relationship
    parent_id = Column(Integer, ForeignKey('tree_nodes.id'), nullable=True)

    # Define relationship without delete-orphan cascade on the many side
    # Use remote_side to clearly indicate which side is "one" and which is "many"
    children = relationship(
        "TreeNode",
        backref="parent",
        cascade="all",  # Removed delete-orphan
        order_by="TreeNode.title",
        remote_side=[id]  # This indicates the "one" side of the relationship
    )

    def get_path(self):
        """Get the full path from root to this node"""
        if self.parent is None:
            return [self]
        else:
            return self.parent.get_path() + [self]

    @property
    def level(self):
        """Get the nesting level of this node"""
        if self.parent is None:
            return 0
        else:
            return self.parent.level + 1
