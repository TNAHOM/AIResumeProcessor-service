.PHONY: help install test lint format clean dev setup migration migrate

# Default target
help:
	@echo "Available commands:"
	@echo "  setup     - Set up development environment"
	@echo "  install   - Install dependencies"
	@echo "  dev       - Start development server"
	@echo "  test      - Run tests"
	@echo "  lint      - Run linting"
	@echo "  format    - Format code"
	@echo "  migration - Create new database migration"
	@echo "  migrate   - Apply database migrations"
	@echo "  clean     - Clean up temporary files"

# Development setup
setup:
	python scripts/dev_setup.py

# Install dependencies
install:
	pip install -r requirements.txt

# Start development server
dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
test:
	python -m pytest tests/ -v

# Run linting
lint:
	flake8 app/ tests/ --max-line-length=88 --extend-ignore=E203,W503
	
# Format code
format:
	black app/ tests/ scripts/
	isort app/ tests/ scripts/

# Create new migration
migration:
	alembic revision --autogenerate -m "$(MESSAGE)"

# Apply migrations
migrate:
	alembic upgrade head

# Clean up
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf .coverage