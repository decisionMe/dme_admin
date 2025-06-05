# models/tree_node.py
# models/cms.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.orm import Session
from database import Base

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
    sequence = Column(Integer, nullable=True)

    # Self-referential relationship
    parent_id = Column(Integer, ForeignKey('tree_nodes.id'), nullable=True)

    # Define relationship without delete-orphan cascade on the many side
    # Use remote_side to clearly indicate which side is "one" and which is "many"
    children = relationship(
        "TreeNode",
        backref="parent",
        cascade="save-update, merge",
        order_by="TreeNode.title",
        remote_side=[id]  # This indicates the "one" side of the relationship
    )

    def get_path(self):
        """Get the full path from root to this node"""
        if self.parent is None:
            return [self]
        else:
            return self.parent.get_path() + [self]

    def reset_sequence(db: Session):
        sequence = 0
        root_nodes = db.query(TreeNode).filter(TreeNode.parent_id == None).order_by(TreeNode.id.asc()).all()

        def set_children_sequence(node):
            local_sequence = 0
            # get all children to that `node.id`
            children = db.query(TreeNode).filter(TreeNode.parent_id == node.id).order_by(TreeNode.id.asc()).all()

            for child in children:
                child.sequence = local_sequence

                db.add(child)
                db.commit()

                local_sequence += 1
                # recursive call to the child node
                set_children_sequence(child)

        # root node fetch
        for node in root_nodes:
            node.sequence = sequence

            db.add(node)
            db.commit()

            sequence += 1
            # in case we have children, set their sequence
            set_children_sequence(node)

    def get_nodes(db: Session, self_id: int = None):
        from models.tree_node import TreeNode

        # Fetch nodes without parent
        root_nodes = db.query(TreeNode).filter(TreeNode.parent_id == None, TreeNode.id != self_id).order_by(TreeNode.sequence.asc(), TreeNode.parent_id.asc()).all()
        
        # Fetch children nodes
        def get_children(node, level=1):
            children = db.query(TreeNode).filter(TreeNode.parent_id == node.id, TreeNode.id != self_id).order_by(TreeNode.sequence.asc()).all()
            
            return [
                {
                    "id": child.id,
                    "title": child.title,
                    "is_expanded": child.is_expanded,
                    "is_document": child.is_document,
                    "is_url": child.is_url,
                    "external_url": child.external_url,
                    "html_content": child.html_content,
                    "level": level,
                    "sequence": child.sequence,
                    "parent_id": child.parent_id,
                    "children": get_children(child, level + 1)
                } for child in children
            ]

        node_list = [
            {
                "id": node.id,
                "title": node.title,
                "is_expanded": node.is_expanded,
                "is_document": node.is_document,
                "is_url": node.is_url,
                "external_url": node.external_url,
                "html_content": node.html_content,
                "level": 0,
                "sequence": node.sequence,
                "parent_id": node.parent_id,
                "children": get_children(node, 1)
            } for node in root_nodes
        ]

        return node_list

    def get_node_by_id(node_id: int, db: Session):
        return db.query(TreeNode).filter(TreeNode.id == node_id).first()

    @property
    def level(self):
        """Get the nesting level of this node"""
        if self.parent is None:
            return 0
        else:
            return self.parent.level + 1
