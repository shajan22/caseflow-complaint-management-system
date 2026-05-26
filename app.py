from flask import Flask, render_template, request, redirect, url_for, session, flash,jsonify
import sqlite3
import joblib
import random
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from langdetect import detect
import joblib
import re
from indicnlp.tokenize import indic_tokenize







try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey')

# Auto-download NLTK resources safely
required_nltk_resources = ['punkt', 'stopwords', 'wordnet']

for resource in required_nltk_resources:
    try:
        nltk.data.find(f'tokenizers/{resource}' if resource == 'punkt' else f'corpora/{resource}')
    except LookupError:
        nltk.download(resource)
# Email Configuration (Use your Gmail credentials or an app password)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_SENDER = os.environ.get('APP_EMAIL_SENDER', os.environ.get('EMAIL_SENDER', ''))
EMAIL_PASSWORD = os.environ.get('APP_EMAIL_PASSWORD', os.environ.get('EMAIL_PASSWORD', ''))
# Load new model and vectorizer
model = joblib.load('complaint_classifier_model.pkl')
vectorizer = joblib.load('tfidf_vectorizer.pkl')
# Load Tamil model and vectorizer
tam_model = joblib.load("tamil_complaint_classifier.pkl")
tam_vectorizer = joblib.load("tamil_tfidf_vectorizer.pkl")

# Database setup
DATABASE = 'app.db'

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Create the 'users' table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        
        # Create the 'complaints' table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                category TEXT,
                urgency_level TEXT,
                timestamp TEXT,
                status TEXT DEFAULT 'Pending',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Check if required columns exist, and add if missing
        cursor.execute("PRAGMA table_info(complaints)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'timestamp' not in columns:
            cursor.execute("ALTER TABLE complaints ADD COLUMN timestamp TEXT")
        
        if 'status' not in columns:
            cursor.execute("ALTER TABLE complaints ADD COLUMN status TEXT DEFAULT 'Pending'")
        
        conn.commit()

init_db()

# Map categories to urgency
category_to_urgency = {
    "Financial Fraud": "Medium",
    "Social Media Abuse": "Low",
    "Cyberbullying": "Medium",
    "Hacking": "High",
    "Sexual Harassment": "High",
    "Cyber Attack": "High",
    "Online Trafficking": "High",
    "Cryptocurrency Scam": "Medium"
}
category_to_email = {
    "Financial Fraud": "cybercrime-financial@example.com",
    "Social Media Abuse": "socialmedia-report@example.com",
    "Cyberbullying": "bullywatch@example.com",
    "Hacking": "infosec-response@example.com",
    "Sexual Harassment": "women-safety@example.com",
    "Cyber Attack": "cyberdefense@example.com",
    "Online Trafficking": "anti-trafficking@example.com",
    "Cryptocurrency Scam": "crypto-alerts@example.com"
}
tamil_category_to_urgency = {
    "மின்னணு மோசடி": "Medium",         # Financial Fraud
    "சமூக ஊடக துஷ்பிரயோகம்": "Low",     # Social Media Abuse
    "இணைய துன்புறுத்தல்": "Medium",      # Cyberbullying
    "ஹேக்கிங்": "High",                  # Hacking
    "பாலியல் தொல்லை": "High",           # Sexual Harassment
    "இணைய தாக்குதல்": "High",           # Cyber Attack
    "ஆன்லைன் கடத்தல்": "High",          # Online Trafficking
    "கிரிப்டோ கரன்சி மோசடி": "Medium"     # Cryptocurrency Scam
}
tamil_category_to_email = {
    "மின்னணு மோசடி": "cybercrime-financial@example.com",
    "சமூக ஊடக துஷ்பிரயோகம்": "socialmedia-report@example.com",
    "இணைய துன்புறுத்தல்": "bullywatch@example.com",
    "ஹேக்கிங்": "infosec-response@example.com",
    "பாலியல் தொல்லை": "women-safety@example.com",
    "இணைய தாக்குதல்": "cyberdefense@example.com",
    "ஆன்லைன் கடத்தல்": "anti-trafficking@example.com",
    "கிரிப்டோ கரன்சி மோசடி": "crypto-alerts@example.com"
}

# Ensure NLTK resources are available
required_nltk_resources = ['punkt', 'stopwords', 'wordnet']
for res in required_nltk_resources:
    try:
        nltk.data.find(f'tokenizers/{res}' if res == 'punkt' else f'corpora/{res}')
    except LookupError:
        nltk.download(res)

# Preprocessing function
stop_words = set(stopwords.words('english'))
lemmatizer = WordNetLemmatizer()

def preprocess_text(text):
    text = text.lower()
    text = re.sub(r'[^a-z\s]', '', text)  # remove punctuation/numbers
    tokens = nltk.word_tokenize(text)     # tokenize
    tokens = [lemmatizer.lemmatize(word) for word in tokens if word not in stop_words]
    return ' '.join(tokens)
def preprocess_tamil(text):
    text = re.sub(r'[^அ-ஹௌஂஃா-்\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    tokens = list(indic_tokenize.trivial_tokenize(text, lang='ta'))
    tokens = [tok for tok in tokens if len(tok.strip()) > 1]
    return ' '.join(tokens)


def reset_data():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM complaints")
        cursor.execute("DELETE FROM users")
        conn.commit()

# Function to calculate urgency based on category
def calculate_urgency(category):
    return category_to_urgency.get(category, "Low")

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            user = cursor.fetchone()
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            if username == 'admin':  # Static admin login
                return redirect(url_for('admin_dashboard'))
            flash('Login successful!', 'success')
            return redirect(url_for('submit_complaint'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
                flash('Registration successful! Please log in.')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Username already exists')
    return render_template('register.html')
@app.route('/submit_complaint', methods=['GET', 'POST'])
def submit_complaint():
    if 'user_id' not in session:
        flash('Please log in to submit a complaint.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        description = request.form['description']
        try:
            language = detect(description)
        except:
            language = 'en'  # fallback if detection fails
                # Route based on language
        if language == 'ta':
            cleaned_text = preprocess_tamil(description)
            transformed_desc = tam_vectorizer.transform([cleaned_text])
            category = tam_model.predict(transformed_desc)[0]
            urgency = tamil_category_to_urgency.get(category, "Medium")
        else:
        # Preprocess & predict
            cleaned_text = preprocess_text(description)  # use your NLP cleaning function
            transformed_desc = vectorizer.transform([cleaned_text])
            category = model.predict(transformed_desc)[0]
            urgency = category_to_urgency.get(category, "Medium")
        complaint_id = random.randint(1000, 9999)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status = 'Pending'

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO complaints (user_id, description, category, urgency_level, timestamp, status) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], description, category, urgency, timestamp, status))
            conn.commit()

        return render_template('result.html', complaint_id=complaint_id, category=category, urgency=urgency, timestamp=timestamp)

    return render_template('submit_complaint.html')


# @app.route('/submit_complaint', methods=['GET', 'POST'])
# def submit_complaint():
#     if 'user_id' not in session:
#         flash('Please log in to submit a complaint.')
#         return redirect(url_for('login'))
    
#     if request.method == 'POST':
#         description = request.form['description']
#         transformed_desc = vectorizer.transform([description])
#         category = model.predict(transformed_desc)[0]
#         urgency = calculate_urgency(category)
#         complaint_id = random.randint(1000, 9999)
#         timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Get current date and time
#         status = 'Pending'  # Default status on complaint submission

#         with sqlite3.connect(DATABASE) as conn:
#             cursor = conn.cursor()
#             cursor.execute('''
#                 INSERT INTO complaints (user_id, description, category, urgency_level, timestamp, status) 
#                 VALUES (?, ?, ?, ?, ?, ?)
#             ''', (session['user_id'], description, category, urgency, timestamp, status))
#             conn.commit()

#         return render_template('result.html', complaint_id=complaint_id, category=category, urgency=urgency, timestamp=timestamp)
    
#     return render_template('submit_complaint.html')
@app.route('/update_status/<int:complaint_id>', methods=['POST'])
def update_status(complaint_id):
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    new_status = request.form['status']
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE complaints SET status = ? WHERE id = ?", (new_status, complaint_id))
        conn.commit()

    flash(f'Status updated for Complaint ID {complaint_id}')
    return redirect(url_for('admin_dashboard'))


    
    return render_template('submit_complaint.html')
# Admin Login
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Static admin login check
        if username == 'admin' and password == 'admin':  # Admin static login
            session['username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'error')
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    search_query = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    urgency_filter = request.args.get('urgency', '').strip()

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Base query and params
        query = '''
            SELECT complaints.id, users.username, complaints.description, complaints.category,
                   complaints.urgency_level, complaints.timestamp, complaints.status
            FROM complaints
            JOIN users ON complaints.user_id = users.id
            WHERE 1=1
        '''
        params = []

        # Add filters
        if search_query:
            query += ' AND (users.username LIKE ? OR complaints.description LIKE ?)'
            params.extend([f'%{search_query}%', f'%{search_query}%'])

        if status_filter in ('Pending', 'Completed'):
            query += ' AND complaints.status = ?'
            params.append(status_filter)

        if urgency_filter in ('Low', 'Medium', 'High'):
            query += ' AND complaints.urgency_level = ?'
            params.append(urgency_filter)

        query += ' ORDER BY complaints.timestamp DESC'

        cursor.execute(query, params)
        complaints = cursor.fetchall()

    return render_template('admin_dashboard.html', complaints=complaints,
                           search_query=search_query,
                           status_filter=status_filter,
                           urgency_filter=urgency_filter)
@app.route('/admin_analytics')
def admin_analytics():
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM complaints')
        total_complaints = cursor.fetchone()[0]

        cursor.execute('SELECT status, COUNT(*) FROM complaints GROUP BY status')
        status_counts = dict(cursor.fetchall())

        cursor.execute('SELECT urgency_level, COUNT(*) FROM complaints GROUP BY urgency_level')
        urgency_counts = dict(cursor.fetchall())

    return render_template('admin_analytics.html',
                           total_complaints=total_complaints,
                           status_counts=status_counts,
                           urgency_counts=urgency_counts)


@app.route('/delete_complaint/<int:complaint_id>', methods=['POST'])
def delete_complaint(complaint_id):
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))
    
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM complaints WHERE id = ?", (complaint_id,))
        conn.commit()
    
    return redirect(url_for('admin_dashboard'))
@app.route('/view_complaint/<int:complaint_id>')
def view_complaint(complaint_id):
    if 'username' not in session or session['username'] != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('admin_login'))
    
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT complaints.id, users.username, complaints.description, complaints.category, 
                   complaints.urgency_level, complaints.timestamp 
            FROM complaints 
            JOIN users ON complaints.user_id = users.id
            WHERE complaints.id = ?
        ''', (complaint_id,))
        complaint = cursor.fetchone()
    
    if not complaint:
        flash('Complaint not found!')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('view_complaint.html', complaint=complaint)


@app.route('/user_complaints')
def user_complaints():
    if 'user_id' not in session:
        flash('Please log in to view your complaints.')
        return redirect(url_for('login'))

    filter_status = request.args.get('status')  # Get filter from URL query, e.g. /user_complaints?status=Pending

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        if filter_status in ('Pending', 'Completed'):
            cursor.execute('''
                SELECT id, description, category, urgency_level, timestamp, status
                FROM complaints 
                WHERE user_id = ? AND status = ?
            ''', (session['user_id'], filter_status))
        else:
            cursor.execute('''
                SELECT id, description, category, urgency_level, timestamp, status
                FROM complaints 
                WHERE user_id = ?
            ''', (session['user_id'],))

        user_complaints = cursor.fetchall()

    return render_template('user_complaints.html', user_complaints=user_complaints, filter_status=filter_status)


@app.route('/send_email/<int:complaint_id>', methods=['POST'])
def send_email(complaint_id):
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT complaints.id, users.username, complaints.description, complaints.category, 
                   complaints.urgency_level, complaints.timestamp 
            FROM complaints 
            JOIN users ON complaints.user_id = users.id
            WHERE complaints.id = ?
        ''', (complaint_id,))
        complaint = cursor.fetchone()

    if not complaint:
        return jsonify({"status": "error", "message": "Complaint not found"}), 404

    complaint_id, username, description, category, urgency, timestamp = complaint

# 🔍 Try English email mapping first, then Tamil
    recipient_email = category_to_email.get(category) or tamil_category_to_email.get(category)
    if not recipient_email:
        return jsonify({"status": "error", "message": "No department email found for this category"}), 400

    subject = f"Complaint Notification - ID {complaint_id} (Urgency: {urgency})"
    message = f"""
    Dear {category} Team,

    A new complaint has been reported.

    📌 Complaint Details:
    - Complaint ID: {complaint_id}
    - Username: {username}
    - Category: {category}
    - Urgency Level: {urgency}
    - Description: {description}
    - Registered Date and Time: {timestamp}

    Please take the necessary action.

    Regards,
    Admin
    """

    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = recipient_email

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, recipient_email, msg.as_string())
        server.quit()

        return jsonify({"status": "success", "message": f"Email sent to {recipient_email}"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/reset_db')
def reset_db():
    if 'username' not in session or session['username'] != 'admin':
        flash('Unauthorized access')
        return redirect(url_for('login'))

    reset_data()
    flash('✅ All data has been reset successfully.')
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
