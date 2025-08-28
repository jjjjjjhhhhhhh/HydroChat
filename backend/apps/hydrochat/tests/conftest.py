"""
Pytest configuration for HydroChat tests
"""
import os
import django
from django.conf import settings

def pytest_configure():
    """Configure Django for testing"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
