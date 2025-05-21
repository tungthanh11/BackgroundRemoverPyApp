import mysql.connector
from dotenv import load_dotenv
import os

from ses_helper import get_email_verification_status

load_dotenv()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        port=os.getenv('DB_PORT')
    )

def get_user_by_username_and_password(username, password):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
    user = cursor.fetchone()
    cursor.close()
    connection.close()
    return user

def get_user_attempts(username):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute('SELECT login_attempts FROM users WHERE username = %s', (username,))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    return result

def update_user_attempts(username, attempts):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('UPDATE users SET login_attempts = %s WHERE username = %s', (attempts, username))
    connection.commit()
    cursor.close()
    connection.close()

def create_user(username, password_hash, email):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('INSERT INTO users (username, password, email) VALUES (%s, %s, %s)', (username, password_hash, email))
    connection.commit()
    cursor.close()
    connection.close()

def update_verification_status(email):
    status = get_email_verification_status(email)
    print(f"Trạng thái xác minh email {email}: {status}")
    if status == "Success":
        connection = get_db_connection()
        cursor = connection.cursor()
  
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        if user:
            cursor.execute('UPDATE users SET verified = %s WHERE email = %s', (True, email))
            connection.commit()
            print(f"{email} đã được xác minh và cập nhật trong database.")
            result = True
        else:
            print("User không tồn tại trong database.")
            result = False
        cursor.close()
        connection.close()
        return result
    else:
        print(f"{email} chưa xác minh.")
        return False


def is_user_verified(email):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute('SELECT verified FROM users WHERE email = %s', (email,))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    return result['verified'] if result else False
