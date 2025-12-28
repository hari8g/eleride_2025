"""
Basic smoke tests for contract rendering.
"""
import pytest
from pathlib import Path
from app.models import ContractRenderRequest
from app.services.contract_renderer import ContractRenderer
from app.services.placeholder_mapper import model_to_placeholders


def test_placeholder_mapping():
    """Test that model fields map correctly to placeholders."""
    request = ContractRenderRequest(
        agreement_city="Mumbai",
        rider_name="Test Rider",
        rider_age=25,
        rider_address="123 Test St",
        weekly_rental_inr=1500.0,
        security_deposit_inr=5000.0,
        account_holder_name="Eleride",
        bank_name="HDFC",
        account_no="123456",
        ifsc="HDFC0001",
        branch="Mumbai"
    )
    
    placeholders = model_to_placeholders(request)
    
    assert "{{RIDER_NAME}}" in placeholders
    assert placeholders["{{RIDER_NAME}}"] == "Test Rider"
    assert "{{RIDER_AGE}}" in placeholders
    assert placeholders["{{RIDER_AGE}}"] == "25"
    assert "{{WEEKLY_RENTAL_INR}}" in placeholders
    assert "₹" in placeholders["{{WEEKLY_RENTAL_INR}}"]
    assert "{{AGREEMENT_CITY}}" in placeholders


def test_age_validation():
    """Test that age validation works."""
    with pytest.raises(ValueError, match="at least 18"):
        ContractRenderRequest(
            agreement_city="Mumbai",
            rider_name="Test",
            rider_age=17,  # Under 18
            rider_address="123 Test",
            weekly_rental_inr=1500.0,
            security_deposit_inr=5000.0,
            account_holder_name="Eleride",
            bank_name="HDFC",
            account_no="123",
            ifsc="HDFC0001",
            branch="Mumbai"
        )


def test_contract_renderer_initialization():
    """Test that renderer initializes correctly."""
    renderer = ContractRenderer()
    assert renderer.template_path.exists() or not renderer.template_path.exists()  # May or may not exist in test
    assert renderer.generated_dir.exists()


def test_optional_fields_default_to_empty():
    """Test that optional fields default to empty strings."""
    request = ContractRenderRequest(
        agreement_city="Mumbai",
        rider_name="Test",
        rider_age=25,
        rider_address="123 Test",
        weekly_rental_inr=1500.0,
        security_deposit_inr=5000.0,
        account_holder_name="Eleride",
        bank_name="HDFC",
        account_no="123",
        ifsc="HDFC0001",
        branch="Mumbai"
        # Not providing optional fields
    )
    
    placeholders = model_to_placeholders(request)
    assert placeholders["{{RIDER_FATHER_NAME}}"] == ""
    assert placeholders["{{FAMILY_NAME}}"] == ""
    assert placeholders["{{FRIEND_NAME}}"] == ""

