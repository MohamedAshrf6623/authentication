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
from .game_score import GameScore
from .patient import Patient
from .prescription import MPrescription
from .location import Location
from .todo import ToDo

__all__ = [
    'db',
    'Doctor',
    'CareGiver',
    'Medicine',
    'Game',
    'GameScore',
    'Patient',
    'MPrescription',
    'Location',
    'ToDo',
]
