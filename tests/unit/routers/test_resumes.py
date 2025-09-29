"""Test resume router endpoints."""
import uuid
from unittest.mock import Mock, patch

import pytest
from fastapi import UploadFile

from app.db.models import Application, ApplicationStatus


def test_get_application_status_not_found(client):
    """Test getting application status for non-existent application."""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/resumes/{fake_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"


def test_get_application_status_success(client, db_session):
    """Test getting application status for existing application."""
    # Create a test application
    app = Application(
        id=uuid.uuid4(),
        name="John Doe",
        email="john@example.com",
        original_filename="test_resume.pdf",
        status=ApplicationStatus.COMPLETED,
    )
    db_session.add(app)
    db_session.commit()
    
    response = client.get(f"/resumes/{app.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(app.id)
    assert data["original_filename"] == "test_resume.pdf"
    assert data["status"] == "COMPLETED"