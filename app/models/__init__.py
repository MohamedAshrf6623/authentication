"""
Models package initialization.
Import all models to ensure SQLAlchemy can resolve relationships.
"""
from app import db

# Import models in dependency order
from .admin import Admin
from .doctor import Doctor
from .caregiver import CareGiver
from .medicine import Medicine
from .game import Game
from .game_score import GameScore
from .system_log import SystemLog
from .patient import Patient
from .prescription import MPrescription
from .location import Location
from .todo import ToDo

__all__ = [
    'db',
    'Admin',
    'Doctor',
    'CareGiver',
    'Medicine',
    'Game',
    'GameScore',
    'SystemLog',
    'Patient',
    'MPrescription',
    'Location',
    'ToDo',
]
