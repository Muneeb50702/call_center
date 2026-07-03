"""
Nexus Dispatch — Documents Router

Metadata tracking for rate confirmations, PODs, BOLs.
Integrates with email service for document delivery.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, DocumentDB
from auth import get_current_user, CurrentUser

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: str
    doc_type: str
    reference_id: str = ""
    file_path: str = ""
    sent_to_email: str = ""
    sent_at: Optional[datetime] = None
    status: str = "generated"
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentCreate(BaseModel):
    doc_type: str  # rate_confirmation, pod, bol
    reference_id: str  # booking_id or load_id
    file_path: str = ""
    sent_to_email: str = ""


@router.post("/", response_model=DocumentResponse, status_code=201)
async def create_document(
    req: DocumentCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a document record."""
    valid_types = ["rate_confirmation", "pod", "bol"]
    if req.doc_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid doc_type. Must be one of: {valid_types}")

    doc = DocumentDB(
        id=f"DOC-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=user.tenant_id,
        doc_type=req.doc_type,
        reference_id=req.reference_id,
        file_path=req.file_path,
        sent_to_email=req.sent_to_email,
        status="generated",
    )
    db.add(doc)
    await db.flush()
    return DocumentResponse.model_validate(doc, from_attributes=True)


@router.get("/", response_model=List[DocumentResponse])
async def list_documents(
    doc_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List documents with filters."""
    query = select(DocumentDB).where(DocumentDB.tenant_id == user.tenant_id)
    if doc_type:
        query = query.where(DocumentDB.doc_type == doc_type)
    if reference_id:
        query = query.where(DocumentDB.reference_id == reference_id)

    query = query.order_by(DocumentDB.created_at.desc()).limit(limit)
    result = await db.execute(query)
    docs = result.scalars().all()
    return [DocumentResponse.model_validate(d, from_attributes=True) for d in docs]


@router.post("/{doc_id}/send")
async def send_document(
    doc_id: str,
    email: str = Query(..., description="Email address to send the document to"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger sending a document via email."""
    result = await db.execute(
        select(DocumentDB).where(
            DocumentDB.id == doc_id,
            DocumentDB.tenant_id == user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # TODO: Integrate with Resend email service in Phase 5
    doc.sent_to_email = email
    doc.sent_at = datetime.utcnow()
    doc.status = "sent"
    await db.flush()

    return {"id": doc_id, "status": "sent", "sent_to": email}
