# app.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from models import Base, User, Ride
import random
from datetime import datetime
import threading
import time
from twilio.rest import Client

from decouple import config

app = Flask(__name__)



# SQLAlchemy setup
DATABASE_URL = config('DATABASE_URL')  # Read from .env or environment
engine = create_engine(DATABASE_URL)   # Create the SQLAlchemy engine
Base = declarative_base()              # Declare the base for ORM models
Base.metadata.create_all(engine)       # Create all tables

# Session setup
Session = sessionmaker(bind=engine)


# Twilio credentials (replace with your own)
ACCOUNT_SID = config('TWILIO_ACCOUNT_SID')
AUTH_TOKEN =  config('TWILIO_AUTH_TOKEN')
WHATSAPP_NUMBER =  config('TWILIO_WHATSAPP_NUMBER')

client = Client(ACCOUNT_SID, AUTH_TOKEN)

def send_message(to_number, body):
    client.messages.create(
        body=body,
        from_=WHATSAPP_NUMBER,
        to=to_number
    )

def simulate_ride_progress(user_phone_number):
    session = Session()
    user = session.query(User).filter_by(phone_number=user_phone_number).first()
    current_ride = session.query(Ride).filter_by(user_id=user.id, status='driver_assigned').first()

    if current_ride:
        # Simulate driver on the way
        time.sleep(5)
        current_ride.status = 'driver_arrived'
        session.commit()
        send_message(user.phone_number, "Your driver has arrived!")

        # Simulate trip starting
        time.sleep(5)
        current_ride.status = 'on_trip'
        session.commit()
        send_message(user.phone_number, "Your trip has started.")

        # Simulate trip completion
        time.sleep(5)
        current_ride.status = 'completed'
        current_ride.timestamp = datetime.now()
        session.commit()
        total_fare = current_ride.fare_estimate
        send_message(user.phone_number, f"You have arrived at your destination. Total fare: {total_fare}. Thank you for riding with us!")

        # Reset user ride state
        user.ride_state = None
        session.commit()

    session.close()
@app.route('/sms', methods=['POST'])
def sms_reply():
    session = Session()
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    response = MessagingResponse()
    message = response.message()

    command = incoming_msg.lower()
    user = session.query(User).filter_by(phone_number=from_number).first()

    if user:
        # First, handle ride booking states
        if user.ride_state == 'awaiting_pickup':
            if 'Latitude' in request.values and 'Longitude' in request.values:
                latitude = request.values.get('Latitude')
                longitude = request.values.get('Longitude')
                user.current_latitude = latitude
                user.current_longitude = longitude
                user.ride_state = 'awaiting_destination'
                session.commit()
                message.body("Location received. Please share your destination location.")
            else:
                message.body("Please share your current location using the location feature.")
        elif user.ride_state == 'awaiting_destination':
            if 'Latitude' in request.values and 'Longitude' in request.values:
                dest_latitude = request.values.get('Latitude')
                dest_longitude = request.values.get('Longitude')
                # Save ride details
                new_ride = Ride(
                    user_id=user.id,
                    pickup_location=f"{user.current_latitude},{user.current_longitude}",
                    destination=f"{dest_latitude},{dest_longitude}",
                    ride_type=None,
                    status='requested',
                    timestamp=datetime.now()
                )
                session.add(new_ride)
                user.ride_state = 'awaiting_ride_type'
                session.commit()
                message.body("Destination received. What type of ride would you like? (Economy, Premium)")
            else:
                message.body("Please share your destination location using the location feature.")
        elif user.ride_state == 'awaiting_ride_type':
            ride_type = incoming_msg.capitalize()
            if ride_type in ['Economy', 'Premium']:
                # Update ride with ride type
                current_ride = session.query(Ride).filter_by(user_id=user.id, status='requested').first()
                if current_ride:
                    current_ride.ride_type = ride_type
                    current_ride.driver_name = random.choice(['Alice', 'Bob', 'Charlie'])
                    current_ride.car_details = random.choice(['Toyota Camry - XYZ123', 'Honda Accord - ABC789'])
                    current_ride.estimated_arrival = random.randint(2, 10)
                    current_ride.fare_estimate = f"${random.randint(10, 50)}"
                    current_ride.status = 'driver_assigned'
                    session.commit()
                    user.ride_state = 'ride_in_progress'
                    session.commit()
                    message.body(
                        f"Your {ride_type} ride is confirmed!\n"
                        f"Driver: {current_ride.driver_name}\n"
                        f"Car: {current_ride.car_details}\n"
                        f"ETA: {current_ride.estimated_arrival} minutes\n"
                        f"Fare Estimate: {current_ride.fare_estimate}\n"
                        "You'll receive updates as your driver approaches."
                    )
                    # Start background thread for ride simulation
                    ride_thread = threading.Thread(target=simulate_ride_progress, args=(user.phone_number,))
                    ride_thread.start()
                else:
                    message.body("An error occurred while processing your ride. Please try again.")
            else:
                message.body("Invalid ride type. Please choose 'Economy' or 'Premium'.")
        else:
            # Handle other user states
            if user.state == 'editing_profile':
                if command == 'update name':
                    user.state = 'updating_name'
                    session.commit()
                    message.body("Please enter your new full name:")
                elif command == 'update contact':
                    user.state = 'updating_contact'
                    session.commit()
                    message.body("Please enter your new emergency contact number:")
                elif command == 'cancel':
                    user.state = 'registered'
                    session.commit()
                    message.body("Profile editing canceled. How can we assist you today?")
                else:
                    message.body("Invalid command. Send 'UPDATE NAME', 'UPDATE CONTACT', or 'CANCEL'.")
            elif user.state == 'registered':
                # Process commands
                if command == 'help':
                    message.body(
                        "Available commands:\n"
                        "- EDIT PROFILE\n"
                        "- BOOK RIDE\n"
                        "- RIDE STATUS\n"
                        "- CANCEL RIDE\n"
                        "- HELP"
                    )
                elif command == 'edit profile':
                    user.state = 'editing_profile'
                    session.commit()
                    message.body("You're now in profile editing mode.\nSend 'UPDATE NAME', 'UPDATE CONTACT', or 'CANCEL' to exit.")
                elif command == 'book ride':
                    user.ride_state = 'awaiting_pickup'
                    session.commit()
                    message.body("Please share your current location using WhatsApp's location feature.")
                elif command == 'ride status':
                    current_ride = session.query(Ride).filter_by(user_id=user.id, status='driver_assigned').first()
                    if current_ride:
                        message.body(f"Your driver is on the way! ETA: {current_ride.estimated_arrival} minutes.")
                    else:
                        message.body("You have no ongoing rides.")
                elif command == 'cancel ride':
                    user.ride_state = None
                    current_ride = session.query(Ride).filter_by(user_id=user.id, status='requested').first()
                    if current_ride:
                        current_ride.status = 'canceled'
                        session.commit()
                        message.body("Your ride has been canceled.")
                    else:
                        message.body("You have no rides to cancel.")
                else:
                    message.body("Send 'HELP' for a list of available commands.")
            else:
                # Handle other states from the signup process
                # ... (existing signup code) ...
                user = User(phone_number=from_number, state='awaiting_name')
                session.add(user)
                session.commit()
                message.body("Welcome to Ride-Hailing App! Please enter your full name:")
            
    else:
        # New user flow
        user = User(phone_number=from_number, state='awaiting_name')
        session.add(user)
        session.commit()
        message.body("Welcome to Ride-Hailing App! Please enter your full name:")

    session.close()
    return str(response)


# @app.route('/sms', methods=['POST'])
# def sms_reply():
#     session = Session()
#     incoming_msg = request.values.get('Body', '').strip()
#     from_number = request.values.get('From', '')
#     response = MessagingResponse()
#     message = response.message()

#     command = incoming_msg.lower()
#     user = session.query(User).filter_by(phone_number=from_number).first()

#     if user:
#         if user.state == 'registered':
#             if command == 'help':
#                 message.body(
#                     "Available commands:\n"
#                     "- EDIT PROFILE\n"
#                     "- BOOK RIDE\n"
#                     "- RIDE STATUS\n"
#                     "- CANCEL RIDE\n"
#                     "- HELP"
#                 )
#             elif command == 'edit profile':
#                 user.state = 'editing_profile'
#                 session.commit()
#                 message.body("You're now in profile editing mode.\nSend 'UPDATE NAME', 'UPDATE CONTACT', or 'CANCEL' to exit.")
#             elif command == 'book ride':
#                 user.ride_state = 'awaiting_pickup'
#                 session.commit()
#                 message.body("Please share your current location using WhatsApp's location feature.")
#             elif command == 'ride status':
#                 current_ride = session.query(Ride).filter_by(user_id=user.id, status='driver_assigned').first()
#                 if current_ride:
#                     message.body(f"Your driver is on the way! ETA: {current_ride.estimated_arrival} minutes.")
#                 else:
#                     message.body("You have no ongoing rides.")
#             elif command == 'cancel ride':
#                 user.ride_state = None
#                 current_ride = session.query(Ride).filter_by(user_id=user.id, status='requested').first()
#                 if current_ride:
#                     current_ride.status = 'canceled'
#                     session.commit()
#                     message.body("Your ride has been canceled.")
#                 else:
#                     message.body("You have no rides to cancel.")
#             else:
#                 message.body("Send 'HELP' for a list of available commands.")
#         elif user.state == 'editing_profile':
#             # ... (profile editing code as before) ...
#             if command == 'update name':
#                 user.state = 'updating_name'
#                 session.commit()
#                 message.body("Please enter your new full name:")
#             elif command == 'update contact':
#                 user.state = 'updating_contact'
#                 session.commit()
#                 message.body("Please enter your new emergency contact number:")
#             elif command == 'cancel':
#                 user.state = 'registered'
#                 session.commit()
#                 message.body("Profile editing canceled. How can we assist you today?")
#             else:
#                 message.body("Invalid command. Send 'UPDATE NAME', 'UPDATE CONTACT', or 'CANCEL'.")
        
#         elif user.ride_state == 'awaiting_pickup':
#             if 'Latitude' in request.values and 'Longitude' in request.values:
#                 latitude = request.values.get('Latitude')
#                 longitude = request.values.get('Longitude')
#                 user.current_latitude = latitude
#                 user.current_longitude = longitude
#                 user.ride_state = 'awaiting_destination'
#                 session.commit()
#                 message.body("Location received. Please share your destination location.")
#             else:
#                 message.body("Please share your current location using the location feature.")
#         elif user.ride_state == 'awaiting_destination':
#             if 'Latitude' in request.values and 'Longitude' in request.values:
#                 dest_latitude = request.values.get('Latitude')
#                 dest_longitude = request.values.get('Longitude')
#                 # Save ride details
#                 new_ride = Ride(
#                     user_id=user.id,
#                     pickup_location=f"{user.current_latitude},{user.current_longitude}",
#                     destination=f"{dest_latitude},{dest_longitude}",
#                     ride_type=None,
#                     status='requested',
#                     timestamp=datetime.now()
#                 )
#                 session.add(new_ride)
#                 user.ride_state = 'awaiting_ride_type'
#                 session.commit()
#                 message.body("Destination received. What type of ride would you like? (Economy, Premium)")
#             else:
#                 message.body("Please share your destination location using the location feature.")
#         elif user.ride_state == 'awaiting_ride_type':
#             ride_type = incoming_msg.capitalize()
#             if ride_type in ['Economy', 'Premium']:
#                 # Update ride with ride type
#                 current_ride = session.query(Ride).filter_by(user_id=user.id, status='requested').first()
#                 if current_ride:
#                     current_ride.ride_type = ride_type
#                     current_ride.driver_name = random.choice(['Alice', 'Bob', 'Charlie'])
#                     current_ride.car_details = random.choice(['Toyota Camry - XYZ123', 'Honda Accord - ABC789'])
#                     current_ride.estimated_arrival = random.randint(2, 10)
#                     current_ride.fare_estimate = f"${random.randint(10, 50)}"
#                     current_ride.status = 'driver_assigned'
#                     session.commit()
#                     user.ride_state = 'ride_in_progress'
#                     session.commit()
#                     message.body(
#                         f"Your {ride_type} ride is confirmed!\n"
#                         f"Driver: {current_ride.driver_name}\n"
#                         f"Car: {current_ride.car_details}\n"
#                         f"ETA: {current_ride.estimated_arrival} minutes\n"
#                         f"Fare Estimate: {current_ride.fare_estimate}\n"
#                         "You'll receive updates as your driver approaches."
#                     )
#                     # Start background thread for ride simulation
#                     ride_thread = threading.Thread(target=simulate_ride_progress, args=(user.phone_number,))
#                     ride_thread.start()
#                 else:
#                     message.body("An error occurred while processing your ride. Please try again.")
#             else:
#                 message.body("Invalid ride type. Please choose 'Economy' or 'Premium'.")
#         else:
#             message.body("An unexpected error occurred. Please send 'HELP' for assistance.")
#     else:
#         # New user flow
#         user = User(phone_number=from_number, state='awaiting_name')
#         session.add(user)
#         session.commit()
#         message.body("Welcome to Ride-Hailing App! Please enter your full name:")

#     session.close()
#     return str(response)

if __name__ == '__main__':
    app.run(debug=True)




# # app.py
# from flask import Flask, request
# from twilio.twiml.messaging_response import MessagingResponse
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker
# from models import Base, User
# import re

# app = Flask(__name__)

# # Database configuration
# engine = create_engine('postgresql://localhost/ride_hailing_db')
# Base.metadata.create_all(engine)
# Session = sessionmaker(bind=engine)

# @app.route('/sms', methods=['POST'])
# def sms_reply():
#     session = Session()
#     incoming_msg = request.values.get('Body', '').strip()
#     from_number = request.values.get('From', '')
#     response = MessagingResponse()
#     message = response.message()

#     command = incoming_msg.lower()
#     user = session.query(User).filter_by(phone_number=from_number).first()

#     if user:
#         if user.state == 'registered':
#             if command == 'help':
#                 message.body("Available commands:\n- EDIT PROFILE\n- HELP\n- (More features coming soon!)")
#             elif command == 'edit profile':
#                 user.state = 'editing_profile'
#                 session.commit()
#                 message.body("You're now in profile editing mode.\nSend 'UPDATE NAME', 'UPDATE CONTACT', or 'CANCEL' to exit.")
#             else:
#                 message.body("Send 'HELP' for a list of available commands.")
#         elif user.state == 'editing_profile':
#             if command == 'update name':
#                 user.state = 'updating_name'
#                 session.commit()
#                 message.body("Please enter your new full name:")
#             elif command == 'update contact':
#                 user.state = 'updating_contact'
#                 session.commit()
#                 message.body("Please enter your new emergency contact number:")
#             elif command == 'cancel':
#                 user.state = 'registered'
#                 session.commit()
#                 message.body("Profile editing canceled. How can we assist you today?")
#             else:
#                 message.body("Invalid command. Send 'UPDATE NAME', 'UPDATE CONTACT', or 'CANCEL'.")
#         elif user.state == 'updating_name':
#             user.full_name = incoming_msg  # Preserve case
#             user.state = 'registered'
#             session.commit()
#             message.body(f"Your name has been updated to {user.full_name}.")
#         elif user.state == 'updating_contact':
#             phone_pattern = re.compile(r'^\+?\d{10,15}$')
#             if phone_pattern.match(incoming_msg):
#                 user.emergency_contact = incoming_msg
#                 user.state = 'registered'
#                 session.commit()
#                 message.body(f"Your emergency contact has been updated to {user.emergency_contact}.")
#             else:
#                 message.body("Invalid phone number format. Please enter a valid phone number including country code.")
#         else:
#             # Handle other states from the signup process
#             if user.state == 'awaiting_name':
#                 user.full_name = incoming_msg
#                 user.state = 'awaiting_role'
#                 session.commit()
#                 message.body("Thank you! Are you a driver or a passenger?")
#             elif user.state == 'awaiting_role':
#                 if command in ['driver', 'passenger']:
#                     user.role = command
#                     user.state = 'awaiting_emergency_contact'
#                     session.commit()
#                     message.body("Please provide an emergency contact number:")
#                 else:
#                     message.body("Invalid role. Please enter 'driver' or 'passenger'.")
#             elif user.state == 'awaiting_emergency_contact':
#                 user.emergency_contact = incoming_msg
#                 user.state = 'registered'
#                 session.commit()
#                 message.body(f"Registration complete! Welcome, {user.full_name}.")
#             else:
#                 user.state = 'registered'
#                 session.commit()
#                 message.body("How can we assist you today?")
#     else:
#         # New user flow
#         user = User(phone_number=from_number, state='awaiting_name')
#         session.add(user)
#         session.commit()
#         message.body("Welcome to Ride-Hailing App! Please enter your full name:")

#     session.close()
#     return str(response)

# if __name__ == '__main__':
#     app.run(debug=True)
