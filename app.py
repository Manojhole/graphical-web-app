import os
import re
import json
import random
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, send_from_directory, abort, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import timedelta

# ---------- CONFIG ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploaded_apps')
STATIC_IMAGES = os.path.join(BASE_DIR, 'static', 'images')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change_this_to_a_secure_random_value'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db = SQLAlchemy(app)

# ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(STATIC_IMAGES, exist_ok=True)

# ---------- MODELS ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    mobile = db.Column(db.String(10), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    hint = db.Column(db.String(256), nullable=True)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class UploadedApp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)


class ImagePassword(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.Integer, db.ForeignKey('uploaded_app.id'), nullable=False, unique=True)
    category = db.Column(db.String(100), nullable=False)
    sequence_hash = db.Column(db.String(512), nullable=False)
    hint = db.Column(db.String(256), nullable=True)

# ---------- HELPERS ----------
def is_valid_mobile(mobile: str) -> bool:
    return re.fullmatch(r'\d{10}', mobile or '') is not None

def user_required():
    return 'user_id' in session

def get_user():
    if not user_required():
        return None
    return User.query.get(session['user_id'])

def list_image_categories():
    cats = []
    images_dir = STATIC_IMAGES
    if os.path.exists(images_dir):
        for name in sorted(os.listdir(images_dir)):
            p = os.path.join(images_dir, name)
            if os.path.isdir(p):
                cats.append(name)
    return cats

def list_images_in_category(cat):
    dirpath = os.path.join(STATIC_IMAGES, cat)
    if not os.path.exists(dirpath) or not os.path.isdir(dirpath):
        return []
    files = sorted([f for f in os.listdir(dirpath) if os.path.isfile(os.path.join(dirpath, f))])
    return files

def app_owned_by_user(app_entry, user_id):
    return app_entry and app_entry.user_id == user_id

def mark_unlocked(app_id):
    unlocked = session.get('unlocked_apps', [])
    if app_id not in unlocked:
        unlocked.append(app_id)
    session['unlocked_apps'] = unlocked

def is_unlocked(app_id):
    return app_id in session.get('unlocked_apps', [])

# ---------- ROUTES ----------
@app.route('/')
def index():
    if user_required():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# ---------- AUTH ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        hint = request.form.get('hint', '').strip()

        if not name or not mobile or not password:
            flash('Name, mobile and password are required.', 'warning')
            return render_template('register.html', name=name, mobile=mobile, hint=hint)

        if not is_valid_mobile(mobile):
            flash('Mobile number must be exactly 10 digits.', 'warning')
            return render_template('register.html', name=name, mobile=mobile, hint=hint)

        if User.query.filter_by(mobile=mobile).first():
            flash('Mobile number already registered. Please login or use another mobile.', 'danger')
            return render_template('register.html', name=name, mobile=mobile, hint=hint)

        user = User(name=name, mobile=mobile, hint=hint)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        if not mobile or not password:
            flash('Enter both mobile and password.', 'warning')
            return render_template('login.html', mobile=mobile)

        user = User.query.filter_by(mobile=mobile).first()
        if user and user.check_password(password):
            session.permanent = True
            session['user_id'] = user.id
            session['user_name'] = user.name
            session.setdefault('unlocked_apps', [])
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid mobile or password.', 'danger')
            return render_template('login.html', mobile=mobile)

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():
    if not user_required():
        return redirect(url_for('login'))
    return render_template('dashboard.html', user_name=session.get('user_name'))

# ---------- FORGOT PASSWORD ----------
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        if not is_valid_mobile(mobile):
            flash('Enter a valid 10-digit mobile number.', 'warning')
            return render_template('forgot_password.html')

        user = User.query.filter_by(mobile=mobile).first()
        if not user:
            flash('No account found with that mobile number.', 'danger')
            return render_template('forgot_password.html')

        flash('Stored hint:', 'info')
        return render_template('forgot_password.html', hint=user.hint, mobile=mobile)

    return render_template('forgot_password.html')

# ---------- UPLOAD WEB-APPS ----------
@app.route('/add-webapp', methods=['GET', 'POST'])
def add_webapp():
    if not user_required():
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('Please choose an HTML file.', 'warning')
            return render_template('add_webapp.html')

        if not file.filename.lower().endswith('.html'):
            flash('Only .html files allowed.', 'danger')
            return render_template('add_webapp.html')

        safe_name = secure_filename(file.filename)
        dest = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(dest):
            safe_name = f"{base}_{counter}{ext}"
            dest = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
            counter += 1

        file.save(dest)

        entry = UploadedApp(user_id=session['user_id'], filename=safe_name)
        db.session.add(entry)
        db.session.commit()

        flash('Web-app uploaded.', 'success')
        return redirect(url_for('my_webapps'))

    return render_template('add_webapp.html')


@app.route('/my-webapps')
def my_webapps():
    if not user_required():
        return redirect(url_for('login'))
    apps = UploadedApp.query.filter_by(user_id=session['user_id']).all()
    apps_info = []
    for a in apps:
        ip = ImagePassword.query.filter_by(app_id=a.id).first()
        apps_info.append({
            'id': a.id,
            'filename': a.filename,
            'locked': True if ip else False
        })
    return render_template('my_webapps.html', apps=apps_info)

# ---------- DELETE APP ----------
@app.route('/delete-webapp/<int:app_id>')
def delete_webapp(app_id):
    if not user_required():
        return redirect(url_for('login'))
    app_entry = UploadedApp.query.get(app_id)
    if not app_entry or not app_owned_by_user(app_entry, session['user_id']):
        abort(403)
    ip = ImagePassword.query.filter_by(app_id=app_entry.id).first()
    if ip:
        db.session.delete(ip)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], app_entry.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(app_entry)
    db.session.commit()
    unlocked = session.get('unlocked_apps', [])
    if app_entry.id in unlocked:
        unlocked.remove(app_entry.id)
        session['unlocked_apps'] = unlocked
    flash('Web-app deleted.', 'success')
    return redirect(url_for('my_webapps'))

# ---------- SERVE UPLOADED HTML ----------
@app.route('/uploaded_apps/<path:filename>')
def uploaded_app_file(filename):
    safe_filename = secure_filename(filename)
    full_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    if not os.path.exists(full_path):
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename)

# ---------- API: LIST IMAGES ----------
@app.route('/list-images/<category>')
def api_list_images(category):
    if '/' in category or '\\' in category or category.startswith('.'):
        return jsonify([])
    images = list_images_in_category(category)
    return jsonify(images)

def build_shuffled_all_images():
    cats = list_image_categories()
    combined = []
    for c in cats:
        files = list_images_in_category(c)
        for f in files:
            combined.append(f"{c}/{f}")
    random.shuffle(combined)
    return combined

# ---------- OPEN LOCKED WEBAPP ----------
@app.route('/open/<int:app_id>', methods=['GET'])
def open_webapp(app_id):
    if not user_required():
        return redirect(url_for('login'))

    app_entry = UploadedApp.query.get(app_id)
    if not app_entry or not app_owned_by_user(app_entry, session['user_id']):
        abort(403)

    ip = ImagePassword.query.filter_by(app_id=app_id).first()
    if not ip:
        flash('No image password set.', 'info')
        return redirect(url_for('set_image_password', app_id=app_id))

    if is_unlocked(app_id):
        return redirect(url_for('uploaded_app_file', filename=app_entry.filename))

    mixed = build_shuffled_all_images()
    return render_template('lock_screen.html', app_id=app_id, mixed_images=mixed, password_category=ip.category, filename=app_entry.filename)

# ---------- SET IMAGE PASSWORD ----------
@app.route('/set-image-password/<int:app_id>', methods=['GET', 'POST'])
def set_image_password(app_id):
    if not user_required():
        return redirect(url_for('login'))
    app_entry = UploadedApp.query.get(app_id)
    if not app_entry or not app_owned_by_user(app_entry, session['user_id']):
        abort(403)

    if request.method == 'POST':
        category = request.form.get('category')
        seq_raw = request.form.get('sequence')
        hint = request.form.get('hint', '').strip()
        if not category or not seq_raw:
            flash('Choose category and images.', 'warning')
            return redirect(url_for('set_image_password', app_id=app_id))

        try:
            seq_list = json.loads(seq_raw)
            if not isinstance(seq_list, list):
                raise ValueError()
        except Exception:
            seq_list = [s for s in seq_raw.split(',') if s]

        if len(seq_list) < 1:
            flash('Select at least one image.', 'warning')
            return redirect(url_for('set_image_password', app_id=app_id))

        normalized = []
        for item in seq_list:
            if '/' in item:
                normalized.append(item)
            else:
                normalized.append(f"{category}/{item}")

        seq_joined = '|'.join(normalized)
        seq_hash = generate_password_hash(seq_joined)

        ip = ImagePassword.query.filter_by(app_id=app_id).first()
        if ip:
            ip.category = category
            ip.sequence_hash = seq_hash
            ip.hint = hint
        else:
            ip = ImagePassword(app_id=app_id, category=category, sequence_hash=seq_hash, hint=hint)
            db.session.add(ip)

        db.session.commit()
        flash('Image password updated.', 'success')
        return redirect(url_for('my_webapps'))

    categories = list_image_categories()
    return render_template('set_image_password.html', app_id=app_id, categories=categories)

# ---------- UNLOCK ----------
@app.route('/unlock/<int:app_id>', methods=['POST'])
def unlock_webapp(app_id):
    if not user_required():
        return jsonify({'ok': False, 'msg': 'Not authenticated'}), 401

    app_entry = UploadedApp.query.get(app_id)
    if not app_entry or not app_owned_by_user(app_entry, session['user_id']):
        return jsonify({'ok': False, 'msg': 'Unauthorized'}), 403

    ip = ImagePassword.query.filter_by(app_id=app_id).first()
    if not ip:
        return jsonify({'ok': False, 'msg': 'No image password set'}), 400

    data = request.get_json() or {}
    seq_list = data.get('sequence')
    if not isinstance(seq_list, list) or len(seq_list) < 1:
        return jsonify({'ok': False, 'msg': 'Invalid sequence'}), 400

    normalized = []
    for item in seq_list:
        if '/' in item:
            normalized.append(item)
        else:
            normalized.append(f"{ip.category}/{item}")

    seq_joined = '|'.join(normalized)
    if check_password_hash(ip.sequence_hash, seq_joined):
        mark_unlocked(app_id)
        file_url = url_for('uploaded_app_file', filename=app_entry.filename)
        return jsonify({'ok': True, 'msg': 'Unlocked', 'url': file_url})
    else:
        return jsonify({'ok': False, 'msg': 'Incorrect sequence'}), 403

# ---------- FORGOT IMAGE PASSWORD ----------
@app.route('/forgot-image-password/<int:app_id>', methods=['GET', 'POST'])
def forgot_image_password(app_id):
    if not user_required():
        return redirect(url_for('login'))
    app_entry = UploadedApp.query.get(app_id)
    if not app_entry or not app_owned_by_user(app_entry, session['user_id']):
        abort(403)
    ip = ImagePassword.query.filter_by(app_id=app_entry.id).first()
    if not ip:
        flash('No image password set for this app.', 'info')
        return redirect(url_for('my_webapps'))

    if request.method == 'POST':
        flash('Stored hint:', 'info')
        return render_template('forgot_image_password.html', hint=ip.hint, app_id=app_id)
    return render_template('forgot_image_password.html', app_id=app_id)


@app.cli.command('init-db')
def init_db():
    db.create_all()
    print("DB initialized.")


# ---------- RUN SERVER ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=False)
