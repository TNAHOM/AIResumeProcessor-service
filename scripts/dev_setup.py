#!/usr/bin/env python3
"""Development setup script for the ATS Resume Parser Service."""

import os
import subprocess
import sys
from pathlib import Path

def run_command(cmd: str, description: str) -> bool:
    """Run a shell command and return success status."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False

def main():
    """Main setup function."""
    print("🚀 Setting up ATS Resume Parser Service for development...")
    
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    steps = [
        ("python -m venv .venv", "Creating virtual environment"),
        ("source .venv/bin/activate && python -m pip install --upgrade pip", "Upgrading pip"),
        ("source .venv/bin/activate && pip install -r requirements.txt", "Installing dependencies"),
        ("source .venv/bin/activate && pip install black isort flake8", "Installing dev tools"),
    ]
    
    # Check if .env file exists
    env_file = project_root / ".env"
    if not env_file.exists():
        print("⚠️  Creating .env file from template...")
        env_template = """# Database Configuration
DB_URL=postgresql://postgres:password@localhost:5432/resume_db

# AWS Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_DEFAULT_REGION=us-east-1
AWS_S3_BUCKET_NAME=your-resume-bucket

# Gemini Configuration
GEMINI_API_KEY=your_gemini_api_key
"""
        env_file.write_text(env_template)
        print("✅ Created .env file - please update with your credentials")
    
    # Run setup steps
    success_count = 0
    for cmd, description in steps:
        if run_command(cmd, description):
            success_count += 1
    
    print(f"\n📊 Setup Summary: {success_count}/{len(steps)} steps completed successfully")
    
    if success_count == len(steps):
        print("\n🎉 Development environment setup complete!")
        print("\nNext steps:")
        print("1. Update the .env file with your actual credentials")
        print("2. Start the development server: uvicorn app.main:app --reload")
        print("3. Visit http://127.0.0.1:8000/docs for API documentation")
    else:
        print("\n⚠️  Some setup steps failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()