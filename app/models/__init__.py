"""
Models package initialization.
Import all models to ensure SQLAlchemy can resolve relationships.
"""
from app import db

# Import models in dependency order
from .doctor import Doctor
from .caregiver import CareGiver
from .medicine import Medicine
from .game import Game
from .patient import Patient
from .prescription import MPrescription

__all__ = [
    'db',
    'Doctor',
    'CareGiver',
    'Medicine',
    'Game',
    'Patient',
    'MPrescription',
]
