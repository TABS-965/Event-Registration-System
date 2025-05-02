from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
import sqlite3
from datetime import datetime
import re
import hashlib

app = Flask(__name__)
app.secret_key = 'your_secret_key_123456789'

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        date TEXT NOT NULL,
        location TEXT NOT NULL,
        created_by INTEGER,
        FOREIGN KEY (created_by) REFERENCES users (id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER,
        user_id INTEGER,
        user_name TEXT NOT NULL,
        user_email TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user'
    )''')
    # Insert default admin user if not exists
    c.execute("SELECT COUNT(*) FROM users WHERE email = 'adminuser@gmail.com'")
    if c.fetchone()[0] == 0:
        hashed_password = hashlib.sha256('admin123'.encode()).hexdigest()
        try:
            c.execute("INSERT INTO users (email, password, name, role) VALUES (?, ?, ?, ?)",
                      ('adminuser@gmail.com', hashed_password, 'Admin User', 'admin'))
            conn.commit()
        except sqlite3.IntegrityError:
            print("Admin user insertion failed due to email conflict.")
    # Insert sample events if table is empty
    c.execute("SELECT COUNT(*) FROM events")
    if c.fetchone()[0] == 0:
        sample_events = [
            ('Tech Conference 2025', 'Annual tech conference with industry leaders', '2025-06-15', 'Convention Center', 1),
            ('AI Workshop', 'Hands-on AI development workshop', '2025-07-10', 'Tech Hub', 1),
            ('Data Science Summit', 'Explore the latest in data science', '2025-08-20', 'City Hall', 1),
        ]
        c.executemany("INSERT INTO events (title, description, date, location, created_by) VALUES (?, ?, ?, ?, ?)", sample_events)
        conn.commit()
    conn.close()

# Validate email format
def is_valid_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email)

# Validate date format (YYYY-MM-DD)
def is_valid_date(date_str):
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

# Check if user is logged in
def login_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# Check if user is admin
def admin_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# Home page - Paginated event list
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 5
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM events")
    total_events = c.fetchone()[0]
    total_pages = (total_events + per_page - 1) // per_page
    c.execute("SELECT * FROM events ORDER BY date ASC LIMIT ? OFFSET ?", (per_page, (page - 1) * per_page))
    events = c.fetchall()
    conn.close()
    return render_template('index.html', events=events, page=page, total_pages=total_pages)

# Event details page
@app.route('/event/<int:event_id>')
def event_detail(event_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    event = c.fetchone()
    if not event:
        abort(404)
    c.execute("SELECT r.user_name, r.user_email, u.name FROM registrations r JOIN users u ON r.user_id = u.id WHERE r.event_id = ?", (event_id,))
    registrations = c.fetchall()
    conn.close()
    return render_template('event_detail.html', event=event, registrations=registrations)

# Register for an event
@app.route('/register/<int:event_id>', methods=['GET', 'POST'])
@login_required
def register(event_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    event = c.fetchone()
    if not event:
        abort(404)
    if request.method == 'POST':
        user_name = request.form['name']
        user_email = request.form['email']
        if not user_name or not user_email:
            flash('All fields are required.', 'error')
        elif not is_valid_email(user_email):
            flash('Invalid email format.', 'error')
        else:
            c.execute("SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", (event_id, session['user_id']))
            if c.fetchone():
                flash('You are already registered for this event.', 'error')
            else:
                c.execute("INSERT INTO registrations (event_id, user_id, user_name, user_email) VALUES (?, ?, ?, ?)",
                          (event_id, session['user_id'], user_name, user_email))
                conn.commit()
                flash('Registration successful!', 'success')
                return redirect(url_for('event_detail', event_id=event_id))
    conn.close()
    return render_template('register.html', event_id=event_id)

# Manage registrations
@app.route('/manage/<int:event_id>')
@login_required
def manage(event_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    event = c.fetchone()
    if not event:
        abort(404)
    c.execute("SELECT r.id, r.user_name, r.user_email, u.name FROM registrations r JOIN users u ON r.user_id = u.id WHERE r.event_id = ?", (event_id,))
    registrations = c.fetchall()
    conn.close()
    return render_template('manage.html', event=event, registrations=registrations)

# Delete a registration
@app.route('/delete/<int:registration_id>/<int:event_id>')
@login_required
def delete_registration(registration_id, event_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    if not c.fetchone():
        abort(404)
    if session.get('role') != 'admin':
        c.execute("SELECT user_id FROM registrations WHERE id = ?", (registration_id,))
        reg = c.fetchone()
        if not reg or reg[0] != session['user_id']:
            abort(403)
    c.execute("DELETE FROM registrations WHERE id = ?", (registration_id,))
    conn.commit()
    conn.close()
    flash('Registration deleted!', 'success')
    return redirect(url_for('manage', event_id=event_id))

# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, hashed_password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            session['user_name'] = user[3]
            session['role'] = user[4]
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')

# User signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        name = request.form['name']
        if not email or not password or not name:
            flash('All fields are required.', 'error')
        elif not is_valid_email(email):
            flash('Invalid email format.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        else:
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            conn = sqlite3.connect('database.db')
            c = conn.cursor()
            try:
                c.execute("INSERT INTO users (email, password, name, role) VALUES (?, ?, ?, ?)",
                          (email, hashed_password, name, 'user'))
                conn.commit()
                flash('Signup successful! Please log in.', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Email already exists.', 'error')
            conn.close()
    return render_template('signup.html')

# User dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT e.id, e.title, e.date, e.location FROM registrations r JOIN events e ON r.event_id = e.id WHERE r.user_id = ?",
              (session['user_id'],))
    user_events = c.fetchall()
    if session['role'] == 'admin':
        c.execute("SELECT * FROM events WHERE created_by = ?", (session['user_id'],))
        created_events = c.fetchall()
    else:
        created_events = []
    conn.close()
    return render_template('dashboard.html', user_events=user_events, created_events=created_events)

# Create event (admin only)
@app.route('/create_event', methods=['GET', 'POST'])
@admin_required
def create_event():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        date = request.form['date']
        location = request.form['location']
        if not title or not date or not location:
            flash('Title, date, and location are required.', 'error')
        elif not is_valid_date(date):
            flash('Invalid date format. Use YYYY-MM-DD.', 'error')
        else:
            conn = sqlite3.connect('database.db')
            c = conn.cursor()
            c.execute("INSERT INTO events (title, description, date, location, created_by) VALUES (?, ?, ?, ?, ?)",
                      (title, description, date, location, session['user_id']))
            conn.commit()
            conn.close()
            flash('Event created successfully!', 'success')
            return redirect(url_for('index'))
    return render_template('create_event.html')

# Delete event (admin only)
@app.route('/delete_event/<int:event_id>')
@admin_required
def delete_event(event_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT created_by FROM events WHERE id = ?", (event_id,))
    event = c.fetchone()
    if not event:
        abort(404)
    if event[0] != session['user_id']:
        abort(403)
    c.execute("DELETE FROM registrations WHERE event_id = ?", (event_id,))
    c.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    flash('Event deleted successfully!', 'success')
    return redirect(url_for('index'))

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

# Custom 404 page
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Custom 403 page
@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

if __name__ == '__main__':
    init_db()
    app.run(debug=True)