"""Backward-compatible local entry point. Hosted workers import the factory only."""
from .application import create_app

app = create_app()
