# models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True)
    full_name = Column(String)
    role = Column(String)
    emergency_contact = Column(String)
    state = Column(String)  # To keep track of where the user is in the signup/login process
    ride_state = Column(String) 
    current_latitude = Column(String)
    current_longitude = Column(String)
    
    
# models.py (add Ride model)
class Ride(Base):
    __tablename__ = 'rides'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    pickup_location = Column(String)
    destination = Column(String)
    ride_type = Column(String)
    driver_name = Column(String)
    car_details = Column(String)
    estimated_arrival = Column(Integer)  # in minutes
    fare_estimate = Column(String)
    status = Column(String)  # e.g., 'requested', 'driver_assigned', 'on_trip', 'completed'
    timestamp = Column(DateTime)
