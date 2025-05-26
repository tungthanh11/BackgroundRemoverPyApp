import re
from flask import Blueprint, render_template, request, flash, redirect, send_file, url_for, session
from rembg import remove
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import logging
import os
import time
import hashlib
from db import create_user, get_db_connection, get_user_by_username_and_password, get_user_attempts, update_user_attempts, update_verification_status, get_background_url_by_user_id  
from recognition_helper import detect_labels
from s3_helper import upload_to_s3, get_s3_url
from dotenv import load_dotenv
from ses_helper import verify_email
from urllib.parse import urlparse

load_dotenv()

bp = Blueprint('main', __name__)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
BUCKET_NAME = os.getenv("BUCKET_NAME")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = hashlib.sha256(password.encode()).hexdigest()


        user = get_user_by_username_and_password(username, password_hash)

        if user:
            # Kiểm tra xem người dùng đã xác minh email chưa
            if not user.get('verified'):
                # Thử xác minh lại từ SES
                is_verified = update_verification_status(user['email'])
                if not is_verified:
                    flash('Your email is not verified. Please check your inbox and verify your email before logging in.', 'warning')
                    return redirect(url_for('main.login')) 

            # Nếu đã xác minh thành công thì tiếp tục đăng nhập
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            flash('Login successful', 'success')
            return redirect(url_for('main.upload_file'))

        # Nếu sai mật khẩu hoặc không tìm thấy user
        user_attempts = get_user_attempts(username)
        if user_attempts and user_attempts['login_attempts'] >= 3:
            flash('Your account is locked due to too many failed login attempts.', 'danger')
        else:
            if user_attempts:
                new_attempts = user_attempts['login_attempts'] + 1
                update_user_attempts(username, new_attempts)
            flash('Invalid credentials. Please try again.', 'danger')

    return render_template('login.html')


@bp.route('/', methods=['GET', 'POST'])
def upload_file():
    logged_in = 'user_id' in session


    if 'upload_count' not in session:
        session['upload_count'] = 0


    if request.method == 'POST':
        if not logged_in and session['upload_count'] >= 3:
            flash('You have reached the upload limit. Please log in to continue.', 'danger')
            return render_template('index.html', logged_in=False)


        if 'file' not in request.files:
            flash('No file part in the request', 'danger')
            return render_template('index.html', logged_in=logged_in)


        file = request.files['file']


        if file.filename == '':
            flash('No file selected', 'danger')
            return render_template('index.html', logged_in=logged_in)


        if not allowed_file(file.filename):
            flash('Only PNG, JPG, JPEG files allowed.', 'danger')
            return render_template('index.html', logged_in=logged_in)


        try:
            input_image = Image.open(file.stream).convert("RGBA")
        except UnidentifiedImageError:
            flash('Invalid image file.', 'danger')
            return render_template('index.html', logged_in=logged_in)


        try:
            input_bytes = BytesIO()
            input_image.save(input_bytes, format='PNG')
            input_bytes_value = input_bytes.getvalue()


            output_bytes = remove(input_bytes_value)
            output_image = Image.open(BytesIO(output_bytes))


            filename = f"image_rmbg_{int(time.time())}.png"
            save_path = os.path.join('static', 'processed', filename)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            output_image.save(save_path)


            if not logged_in:
                session['upload_count'] += 1


            # ✅ Gọi Rekognition để phân tích ảnh
            rekog_labels = detect_labels(output_bytes)
            label_names = [label['Name'] for label in rekog_labels]


            img_url = url_for('static', filename=f'processed/{filename}')
            return render_template("result.html", img_url=img_url, filename=filename, labels=label_names, logged_in=logged_in)


        except Exception as e:
            logging.error("Exception occurred", exc_info=True)
            flash(f'Processing failed: {e}', 'danger')
            return render_template('index.html', logged_in=logged_in)


    return render_template('index.html', logged_in=logged_in)

@bp.route('/download/<filename>')
def download_file(filename):
    if not allowed_file(filename):
        flash('Invalid file format for download.', 'danger')
        return redirect(url_for('main.upload_file'))

    file_path = os.path.join('static', 'processed', filename)
    if not os.path.exists(file_path):
        flash("File not found.", 'danger')
        return redirect(url_for('main.upload_file'))

    return send_file(file_path, mimetype='image/png', as_attachment=True, download_name=filename)


# Route đăng xuất
@bp.route('/logout')
def logout():
    session.pop('user_id', None)
    session['upload_count'] = 0 
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.upload_file'))

# Route đăng ký
@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        # Kiểm tra dinh dạng email
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('Invalid email format.', 'danger')
            return render_template('signup.html')
        
        # Mã hóa mật khẩu
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Kiểm tra xem người dùng đã tồn tại chưa
        existing_user = get_user_by_username_and_password(username, password_hash)
        if existing_user:
            flash('Username already exists. Please choose another one.', 'danger')
            return render_template('register.html')

        # goi ham verify_email o ben ses_helper.py
        if not verify_email(email):
            flash('Email verification failed. Please try again.', 'danger')
            return render_template('register.html')
        
        # thong bao da gui email xac thuc
        flash('Verification email sent. Please check your inbox.', 'success')
        
        # Tạo người dùng mới
        create_user(username, password_hash, email)
        
        return redirect(url_for('main.login'))

    return render_template('signup.html')

@bp.route('/change-background/<filename>', methods=['GET'])
def change_background(filename):
    if 'user_id' not in session:
        flash('You need to login to select background.', 'warning')
        return redirect(url_for('main.login'))

    user_id = session['user_id']

    # Kết nối db lấy url_background theo user_id
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute('SELECT url_background FROM images WHERE user_id = %s', (user_id,))
    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    # Lấy danh sách URL background
    background_urls = [row['url_background'] for row in rows]

    return render_template("change_background.html", filename=filename, backgrounds=background_urls, logged_in=user_id)



@bp.route('/apply-background', methods=['POST'])
def apply_background():
    import requests
    from PIL import ImageOps
    from urllib.parse import urlparse

    print("Session inside apply_background:", dict(session))

    filename = request.form.get('filename')
    user_id = session.get('user_id')

    if not filename or not user_id:
        flash("Missing required data to apply background.", 'danger')
        return redirect(url_for('main.upload_file'))

    try:
        background_url = get_background_url_by_user_id(user_id)
        if not background_url:
            flash("No background image found for your account.", 'danger')
            return redirect(url_for('main.upload_file'))

        print("🌐 Background URL:", background_url)

        response = requests.get(background_url)
        response.raise_for_status()
        bg_file = BytesIO(response.content)

        fg_path = os.path.join('static', 'processed', filename)
        foreground = Image.open(fg_path).convert("RGBA")

        background = Image.open(bg_file).convert("RGBA").resize(foreground.size)

        result = Image.alpha_composite(background, foreground)

        new_filename = f"final_{int(time.time())}.png"
        save_path = os.path.join('static', 'processed', new_filename)
        result.save(save_path)

        img_url = url_for('static', filename=f'processed/{new_filename}')
        return render_template("result.html", img_url=img_url, filename=new_filename, logged_in='user_id' in session)

    except Exception as e:
        logging.error("Background change failed", exc_info=True)
        flash(f"Failed to apply background: {e}", 'danger')
        return redirect(url_for('main.upload_file'))

@bp.route('/upload-background', methods=['POST'])
def upload_background():
    from werkzeug.utils import secure_filename

    if 'user_id' not in session:
        flash('You must be logged in to upload a background.', 'danger')
        return redirect(url_for('main.login'))

    user_id = session['user_id']
    print("User ID at upload start:", user_id) 

    background_file = request.files.get('background_file')
    filename_param = request.form.get('filename')

    if not background_file or background_file.filename == '':
        flash('No background file selected.', 'danger')
        return redirect(url_for('main.change_background', filename=filename_param))

    if not allowed_file(background_file.filename):
        flash('Only PNG, JPG, JPEG files are allowed.', 'danger')
        return redirect(url_for('main.change_background', filename=filename_param))

    try:
        filename = secure_filename(background_file.filename)
        timestamped_name = f"remove-background-imgs/{int(time.time())}_{filename}"

        upload_to_s3(background_file, BUCKET_NAME, timestamped_name)
        bg_url = get_s3_url(BUCKET_NAME, timestamped_name)

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO images (user_id, url_background) VALUES (%s, %s)',
            (user_id, bg_url)
        )
        connection.commit()
        cursor.close()
        connection.close()

        flash('Background uploaded successfully. You can now select it.', 'success')
        print("User ID before redirect:", session.get('user_id')) 
        return redirect(url_for('main.change_background', filename=filename_param))

    except Exception as e:
        logging.error("Failed to upload background", exc_info=True)
        flash(f"Failed to upload background: {e}", 'danger')
        return redirect(url_for('main.change_background', filename=filename_param))
