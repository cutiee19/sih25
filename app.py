import os
import random
import smtplib
import sqlite3
import wave
import json
from pathlib import Path
from math import ceil  # module 2
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from flask_bcrypt import Bcrypt

# Use PyMySQL as a drop-in replacement for MySQLdb on Windows
import pymysql
pymysql.install_as_MySQLdb()

from flask_mysqldb import MySQL

# Optional: offline TTS
try:
    import pyttsx3
except Exception:
    pyttsx3 = None

# ---------------- FLASK INIT ----------------
app = Flask(__name__)
app.secret_key = "your_secret_key_here"


# ---------------- MYSQL CONFIG (Login/Signup) ----------------
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'VSjs@2436'   # replace with your real password or use env var
app.config['MYSQL_DB'] = 'digital_learning'

mysql = MySQL(app)
bcrypt = Bcrypt(app)

# ---------------- OFFLINE TTS (pyttsx3) ----------------
engine = None
if pyttsx3 is not None:
    try:
        engine = pyttsx3.init()
    except Exception:
        engine = None

def speak_text(text):
    """Speak text using pyttsx3 if available (non-blocking-ish)."""
    if engine is None:
        # TTS not available — safe fallback (no crash)
        print("[TTS disabled] Would say:", text)
        return
    engine.say(text)
    engine.runAndWait()
# ---------------- DICTIONARY LOOKUP (SQLite) ----------------
BASE_DIR = Path(__file__).parent.resolve()
DICT_DB = BASE_DIR / "dictionary.db"

def get_meanings(word):
    """Look up meanings in local SQLite dictionary.db (english_dict, hindi_dict, punjabi_dict)."""
    if not DICT_DB.exists():
        return {
            "english": "Dictionary DB not found",
            "hindi": "डिक्शनरी मौजूद नहीं",
            "punjabi": "ਡਿਕਸ਼ਨਰੀ ਨਹੀਂ ਮਿਲੀ"
        }
    conn = sqlite3.connect(str(DICT_DB))
    cur = conn.cursor()
    w = word.strip().lower()
    cur.execute("SELECT meaning FROM english_dict WHERE word = ?", (w,))
    eng = cur.fetchone()
    cur.execute("SELECT meaning FROM hindi_dict WHERE word = ?", (w,))
    hin = cur.fetchone()
    cur.execute("SELECT meaning FROM punjabi_dict WHERE word = ?", (w,))
    pan = cur.fetchone()
    conn.close()
    return {
        "english": eng[0] if eng else "Meaning not found",
        "hindi": hin[0] if hin else "शब्द नहीं मिला",
        "punjabi": pan[0] if pan else "ਸ਼ਬਦ ਨਹੀਂ ਮਿਲਿਆ"
    }

# ---------------- EMAIL OTP ----------------
EMAIL_FROM = "sudeshv2601@gmail.com"
EMAIL_APP_PASSWORD = "shhm mabq jlzw wibh"  # consider storing in env var!

def send_email_otp(to_email, otp):
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        subject = "Your OTP Verification Code"
        body = f"Your OTP is {otp}. Use this to complete signup."
        message = f"Subject: {subject}\n\n{body}"
        server.sendmail(EMAIL_FROM, to_email, message)
        server.quit()
        print(f"OTP sent to {to_email}")
    except Exception as e:
        print("Email OTP error:", e)

# ---------------- HELPERS ----------------
def get_mysql_cursor(dict_cursor=False):
    """Return a MySQL cursor. If dict_cursor True, returns dictionary-style cursor."""
    if dict_cursor:
        return mysql.connection.cursor()  # flask_mysqldb returns tuples by default; user can adapt
    return mysql.connection.cursor()

# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return render_template('index.html')

# Signup with OTP
@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', "").strip()
        email = request.form.get('email', "").strip().lower()
        password = request.form.get('password', "")
        confirm = request.form.get('confirm_password', "")
        entered_otp = request.form.get('otp', "")

        if not all([name, email, password, confirm]):
            flash("Please fill all fields.", "danger")
            return redirect(url_for('signup'))

        if password != confirm:
            flash("Passwords do not match!", "danger")
            return redirect(url_for('signup'))

        if 'generated_otp' not in session or str(session['generated_otp']) != str(entered_otp):
            flash("Invalid or missing OTP!", "danger")
            return redirect(url_for('signup'))

        # check if email exists
        cur = get_mysql_cursor()
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cur.fetchone():
            cur.close()
            flash("Email already registered. Please login.", "info")
            return redirect(url_for('home'))

        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        cur.execute(
            "INSERT INTO users(name, email, password, language) VALUES(%s, %s, %s, %s)",
            (name, email, hashed, "English")
        )
        mysql.connection.commit()
        cur.close()
        session.pop('generated_otp', None)
        flash("Signup successful! Please login.", "success")
        return redirect(url_for('home'))

    return render_template('signup.html')

@app.route('/send_otp', methods=['POST'])
def send_otp():
    name=request.form.get('name',"").strip()
    email = request.form.get('email', "").strip().lower()
    if not email:
        flash("Enter your email first.", "danger")
        return redirect(url_for('signup'))
    otp = random.randint(100000, 999999)
    session['generated_otp'] = otp
    session['signup_name']=name
    session['signup_email']=email
    send_email_otp(email, otp)
    flash("OTP sent to your email (check spam).", "info")
    return redirect(url_for('signup'))

# Login
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', "").strip().lower()
        password_candidate = request.form.get('password', "")

        cur = get_mysql_cursor()
        cur.execute("SELECT id, name, email, password, language FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        if user and bcrypt.check_password_hash(user[3], password_candidate):
            session['loggedin'] = True
            session['username'] = user[1]
            session['email'] = user[2]
            session['language'] = user[4] or "English"
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid login credentials", "danger")
            return redirect(url_for('home'))

    return render_template('index.html')

# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():
    if 'loggedin' in session:
        return render_template(
            'dashboard.html',
            username=session.get('username'),
            language=session.get('language', 'English')
        )
    flash("Please log in first.", "warning")
    return redirect(url_for('home'))

# ---------- SET LANGUAGE (POST FORM) ----------
@app.route('/set_language', methods=['POST'])
def set_language():
    if 'loggedin' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('home'))

    lang = request.form.get('lang')   # radio button value
    supported = {'english': 'English', 'hindi': 'Hindi', 'punjabi': 'Punjabi'}
    key = lang.strip().lower() if lang else "english"

    if key in supported:
        session['language'] = supported[key]
        # persist in DB
        try:
            cur = get_mysql_cursor()
            cur.execute("UPDATE users SET language=%s WHERE email=%s", (supported[key], session.get('email')))
            mysql.connection.commit()
            cur.close()
        except Exception as e:
            print("DB update language error:", e)

        flash(f"Language set to {supported[key]}", "success")
    else:
        flash("Unsupported language", "danger")

    return redirect(url_for('dashboard'))

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))

# ---------- helper ----------
def require_login_redirect():
    flash("Please log in first.", "warning")
    return redirect(url_for('home'))

# ---------- PAGE 1 ----------
@app.route('/page1')
def page1():
    if not session.get('loggedin'):
        return require_login_redirect()
    session.pop('current', None)
    session.pop('score', None)
    session.pop('lang', None)
    return render_template("page1.html", username=session.get("username"))

# ---------- PAGE 2 ----------
@app.route('/page2')
def page2():
    if not session.get('loggedin'):
        return require_login_redirect()
    return render_template("page2.html", username=session.get("username"))

# ---------- MODULE 1 ----------
@app.route('/module1')
def module1():
    if not session.get('loggedin'):
        return require_login_redirect()
    return render_template('module1.html', language=session.get('language', 'English'))

# ---------- MODULE 2 (single, corrected) ----------
VOCAB = [
    {"en": "apple", "hi": "सेब", "pa": "ਸੇਬ"},
    {"en": "banana", "hi": "केला", "pa": "ਕੇਲਾ"},
    {"en": "orange", "hi": "संतरा", "pa": "ਸੰਤਰਾ"},
    {"en": "mango", "hi": "आम", "pa": "ਅੰਬ"},
    {"en": "grapes", "hi": "अंगूर", "pa": "ਅੰਗੂਰ"},
    {"en": "water", "hi": "पानी", "pa": "ਪਾਣੀ"},
    {"en": "milk", "hi": "दूध", "pa": "ਦੁੱਧ"},
    {"en": "tea", "hi": "चाय", "pa": "ਚਾਹ"},
    {"en": "coffee", "hi": "कॉफ़ी", "pa": "ਕੌਫੀ"},
    {"en": "juice", "hi": "जूस", "pa": "ਰਸ"},
    {"en": "bread", "hi": "ब्रेड", "pa": "ਰੋਟੀ"},
    {"en": "rice", "hi": "चावल", "pa": "ਚਾਵਲ"},
    {"en": "egg", "hi": "अंडा", "pa": "ਅੰਡਾ"},
    {"en": "fish", "hi": "मछली", "pa": "ਮੱਛੀ"},
    {"en": "chicken", "hi": "चिकन", "pa": "ਚਿਕਨ"},
    {"en": "meat", "hi": "मांस", "pa": "ਮਾਸ"},
    {"en": "fruit", "hi": "फल", "pa": "ਫਲ"},
    {"en": "vegetable", "hi": "सब्ज़ी", "pa": "ਸਬਜ਼ੀ"},
    {"en": "girl", "hi": "लड़की", "pa": "ਕੁੜੀ"},
    {"en": "boy", "hi": "लड़का", "pa": "ਮੁੰਡਾ"},
    {"en": "man", "hi": "आदमी", "pa": "ਆਦਮੀ"},
    {"en": "woman", "hi": "औरत", "pa": "ਔਰਤ"},
    {"en": "child", "hi": "बच्चा", "pa": "ਬੱਚਾ"},
    {"en": "baby", "hi": "शिशु", "pa": "ਬੱਚਾ"},
    {"en": "friend", "hi": "दोस्त", "pa": "ਦੋਸਤ"},
    {"en": "family", "hi": "परिवार", "pa": "ਪਰਿਵਾਰ"},
    {"en": "mother", "hi": "माँ", "pa": "ਮਾਂ"},
    {"en": "father", "hi": "पिता", "pa": "ਪਿਤਾ"},
    {"en": "brother", "hi": "भाई", "pa": "ਭਰਾ"},
    {"en": "sister", "hi": "बहन", "pa": "ਭੈਣ"},
    {"en": "teacher", "hi": "शिक्षक", "pa": "ਅਧਿਆਪਕ"},
    {"en": "student", "hi": "छात्र", "pa": "ਵਿਦਿਆਰਥੀ"},
    {"en": "school", "hi": "स्कूल", "pa": "ਸਕੂਲ"},
    {"en": "book", "hi": "किताब", "pa": "ਕਿਤਾਬ"},
    {"en": "pen", "hi": "पेन", "pa": "ਕਲਮ"},
    {"en": "pencil", "hi": "पेंसिल", "pa": "ਪੈਂਸਿਲ"},
    {"en": "notebook", "hi": "नोटबुक", "pa": "ਨੋਟਬੁੱਕ"},
    {"en": "bag", "hi": "बैग", "pa": "ਬੈਗ"},
    {"en": "chair", "hi": "कुर्सी", "pa": "ਕੁਰਸੀ"},
    {"en": "table", "hi": "मेज़", "pa": "ਮੇਜ਼"},
    {"en": "door", "hi": "दरवाज़ा", "pa": "ਦਰਵਾਜ਼ਾ"},
    {"en": "window", "hi": "खिड़की", "pa": "ਖਿੜਕੀ"},
    {"en": "house", "hi": "घर", "pa": "ਘਰ"},
    {"en": "room", "hi": "कमरा", "pa": "ਕਮਰਾ"},
    {"en": "kitchen", "hi": "रसोई", "pa": "ਰਸੋਈ"},
    {"en": "bathroom", "hi": "बाथरूम", "pa": "ਬਾਥਰੂਮ"},
    {"en": "garden", "hi": "बगीचा", "pa": "ਬਾਗ"},
    {"en": "park", "hi": "पार्क", "pa": "ਪਾਰਕ"},
    {"en": "road", "hi": "सड़क", "pa": "ਸੜਕ"},
    {"en": "city", "hi": "शहर", "pa": "ਸ਼ਹਿਰ"},
    {"en": "village", "hi": "गाँव", "pa": "ਪਿੰਡ"},
    {"en": "country", "hi": "देश", "pa": "ਦੇਸ਼"},
    {"en": "world", "hi": "दुनिया", "pa": "ਦੁਨੀਆ"},
    {"en": "sun", "hi": "सूरज", "pa": "ਸੂਰਜ"},
    {"en": "moon", "hi": "चाँद", "pa": "ਚਾਨਣ"},
    {"en": "star", "hi": "तारा", "pa": "ਤਾਰਾ"},
    {"en": "sky", "hi": "आकाश", "pa": "ਆਕਾਸ਼"},
    {"en": "cloud", "hi": "बादल", "pa": "ਬਦਲ"},
    {"en": "rain", "hi": "बारिश", "pa": "ਮੀਂਹ"},
    {"en": "snow", "hi": "बर्फ़", "pa": "ਬਰਫ਼"},
    {"en": "wind", "hi": "हवा", "pa": "ਹਵਾ"},
    {"en": "fire", "hi": "आग", "pa": "ਅੱਗ"},
    {"en": "tree", "hi": "पेड़", "pa": "ਦਰੱਖਤ"},
    {"en": "flower", "hi": "फूल", "pa": "ਫੁੱਲ"},
    {"en": "grass", "hi": "घास", "pa": "ਘਾਸ"},
    {"en": "mountain", "hi": "पहाड़", "pa": "ਪਹਾੜ"},
    {"en": "river", "hi": "नदी", "pa": "ਦਰਿਆ"},
    {"en": "lake", "hi": "झील", "pa": "ਝੀਲ"},
    {"en": "sea", "hi": "समुद्र", "pa": "ਸਮੁੰਦਰ"},
    {"en": "ocean", "hi": "महासागर", "pa": "ਮਹਾਸਾਗਰ"},
    {"en": "hot", "hi": "गर्म", "pa": "ਗਰਮ"},
    {"en": "cold", "hi": "ठंडा", "pa": "ਠੰਢਾ"},
    {"en": "warm", "hi": "गरम", "pa": "ਗਰਮ"},
    {"en": "cool", "hi": "ठंडा", "pa": "ਠੰਢਾ"},
    {"en": "happy", "hi": "खुश", "pa": "ਖੁਸ਼"},
    {"en": "sad", "hi": "दुखी", "pa": "ਉਦਾਸ"},
    {"en": "angry", "hi": "गुस्सा", "pa": "ਗੁੱਸਾ"},
    {"en": "love", "hi": "प्यार", "pa": "ਪਿਆਰ"},
    {"en": "like", "hi": "पसंद", "pa": "ਪਸੰਦ"},
    {"en": "hate", "hi": "नफ़रत", "pa": "ਨਫ਼ਰਤ"},
    {"en": "big", "hi": "बड़ा", "pa": "ਵੱਡਾ"},
    {"en": "small", "hi": "छोटा", "pa": "ਛੋਟਾ"},
    {"en": "long", "hi": "लंबा", "pa": "ਲੰਮਾ"},
    {"en": "short", "hi": "छोटा", "pa": "ਛੋਟਾ"},
    {"en": "fast", "hi": "तेज़", "pa": "ਤੇਜ਼"},
    {"en": "slow", "hi": "धीमा", "pa": "ਧੀਮਾ"},
    {"en": "up", "hi": "ऊपर", "pa": "ਉੱਪਰ"},
    {"en": "down", "hi": "नीचे", "pa": "ਹੇਠਾਂ"},
    {"en": "left", "hi": "बाएँ", "pa": "ਖੱਬੇ"},
    {"en": "right", "hi": "दाएँ", "pa": "ਸੱਜੇ"},
    {"en": "morning", "hi": "सुबह", "pa": "ਸਵੇਰ"},
    {"en": "afternoon", "hi": "दोपहर", "pa": "ਦੁਪਹਿਰ"},
    {"en": "evening", "hi": "शाम", "pa": "ਸ਼ਾਮ"},
    {"en": "night", "hi": "रात", "pa": "ਰਾਤ"},
    {"en": "today", "hi": "आज", "pa": "ਅੱਜ"},
    {"en": "yesterday", "hi": "कल", "pa": "ਕੱਲ੍ਹ"},
    {"en": "tomorrow", "hi": "कल", "pa": "ਕੱਲ੍ਹ"},
    {"en": "yes", "hi": "हाँ", "pa": "ਹਾਂ"},
    {"en": "no", "hi": "नहीं", "pa": "ਨहीं"},
    {"en": "please", "hi": "कृपया", "pa": "ਕਿਰਪਾ"}
]
@app.route('/module2')
def module2():
    if not session.get('loggedin'):
        return require_login_redirect()

    # Which language did the user select in /set_language?
    selected_label = session.get('language', 'Hindi')  # default to Hindi
    label_to_key = {'English': 'en', 'Hindi': 'hi', 'Punjabi': 'pa'}
    selected_key = label_to_key.get(selected_label, 'hi')

    # back button always goes to dashboard
    back_url = url_for('dashboard')

    return render_template(
        'module2.html',
        vocabulary=VOCAB,
        selected_key=selected_key,
        selected_label=selected_label,
        total_words=len(VOCAB),
        back_url=back_url
    )
#----------------module 3----------------
@app.route('/module3')
def module3():
    # Module 3 content
    module3_data = {
        "Tenses": {
            "English": "Tenses show when an action happens.",
            "Punjabi": "ਕਿਰਿਆ ਦੇ ਸਮੇਂ ਨੂੰ ਦਿਖਾਉਂਦਾ ਹੈ।",
            "Hindi": "क्रिया के समय को दिखाता है।"
        },
        "Pronouns": {
            "English": "Words used instead of nouns to avoid repetition.",
            "Punjabi": "ਨਾਊਨ ਦੀ ਬਜਾਏ ਵਰਤੇ ਜਾਣ ਵਾਲੇ ਸ਼ਬਦ।",
            "Hindi": "संज्ञा के बजाय प्रयोग किए जाने वाले शब्द।"
        },
        "Articles": {
            "English": "Articles are used with nouns.",
            "Punjabi": "ਨਾਉਂ ਦੇ ਨਾਲ ਵਰਤੇ ਜਾਂਦੇ ਹਨ।",
            "Hindi": "संज्ञा के साथ प्रयुक्त होते हैं।"
        },
        "Prepositions": {
            "English": "Words that show place, time, or direction.",
            "Punjabi": "ਸ਼ਬਦ ਜੋ ਸਥਾਨ, ਸਮਾਂ ਜਾਂ ਦਿਸ਼ਾ ਦਿਖਾਉਂਦੇ ਹਨ।",
            "Hindi": "शब्द जो स्थान, समय या दिशा दिखाते हैं।"
        },
        "Conjunctions": {
            "English": "Words that connect clauses or sentences.",
            "Punjabi": "ਸ਼ਬਦ ਜੋ ਵਾਕਾਂ ਜਾਂ ਕਲੌਜ਼ ਨੂੰ ਜੋੜਦੇ ਹਨ।",
            "Hindi": "शब्द जो वाक्यों या वाक्यांशों को जोड़ते हैं।"
        }
    }
    # Types/subcategories for each topic
    module3_types = {
        "Tenses": {
            "English": {
                "Present Simple": "I go to school.",
                "Present Continuous": "I am going to school.",
                "Past Simple": "I went to the market.",
                "Past Continuous": "I was going to the market.",
                "Future Simple": "I will help you tomorrow."
            },
            "Punjabi": {
                "ਵਰਤਮਾਨ ਸਧਾਰਨ": "ਮੈਂ ਸਕੂਲ ਜਾਂਦਾ ਹਾਂ।",
                "ਵਰਤਮਾਨ ਪ੍ਰਗਟ": "ਮੈਂ ਸਕੂਲ ਜਾ ਰਿਹਾ ਹਾਂ।",
                "ਭੂਤਕਾਲ ਸਧਾਰਨ": "ਮੈਂ ਬਜ਼ਾਰ ਗਿਆ ਸੀ।",
                "ਭੂਤਕਾਲ ਪ੍ਰਗਟ": "ਮੈਂ ਬਜ਼ਾਰ ਜਾ ਰਿਹਾ ਸੀ।",
                "ਭਵਿੱਖਕਾਲ ਸਧਾਰਨ": "ਮੈਂ ਕੱਲ੍ਹ ਤੁਹਾਡੀ ਮਦਦ ਕਰਾਂਗਾ।"
            },
            "Hindi": {
                "वर्तमान काल (Present Simple)": "मैं स्कूल जाता हूँ।",
                "वर्तमान प्रगत (Present Continuous)": "मैं स्कूल जा रहा हूँ।",
                "भूतकाल सरल (Past Simple)": "मैं बाजार गया।",
                "भूतकाल प्रगत (Past Continuous)": "मैं बाजार जा रहा था।",
                "भविष्यत काल (Future Simple)": "मैं कल आपकी मदद करूँगा।"
            }
        },
        "Pronouns": {
            "English": {
                "Subject pronouns": "I, you, he, she, it, we, they",
                "Object pronouns": "me, him, her, us, them",
                "Possessive pronouns": "my, your, his, her, our, their"
            },
            "Punjabi": {
                "ਵਿਸ਼ੇ ਪ੍ਰਣਾਊਨ": "ਮੈਂ, ਤੂੰ, ਉਹ, ਉਹ (ਔਰਤ), ਇਹ, ਅਸੀਂ, ਉਹ",
                "ਵਸਤੂ ਪ੍ਰਣਾਊਨ": "ਮੈਨੂੰ, ਉਸਨੂੰ, ਉਸਨੂੰ (ਔਰਤ), ਸਾਨੂੰ, ਉਹਨਾਂ ਨੂੰ",
                "ਸੱਪਤੀ ਪ੍ਰਣਾਊਨ": "ਮੇਰਾ, ਤੇਰਾ, ਉਸਦਾ, ਉਸਦੀ, ਸਾਡਾ, ਉਹਨਾਂ ਦਾ"
            },
            "Hindi": {
                "सर्वनाम (Subject pronouns)": "मैं, तुम, वह, यह, हम, वे",
                "वस्तु सर्वनाम (Object pronouns)": "मुझे, उसे, हमें, उन्हें",
                "संपत्ति सर्वनाम (Possessive pronouns)": "मेरा, तुम्हारा, उसका, हमारा, उनका"
            }
        },
        "Articles": {
            "English": {
                "Indefinite": "a, an (for any one thing)\nExample: I saw a dog.",
                "Definite": "the (for a specific thing)\nExample: The sun is bright."
            },
            "Punjabi": {
                "ਅਨਿਰਧਾਰਿਤ": "a, an (ਕਿਸੇ ਵੀ ਚੀਜ਼ ਲਈ)\nਉਦਾਹਰਨ: ਮੈਂ ਇੱਕ ਕੁੱਤਾ ਦੇਖਿਆ।",
                "ਨਿਰਧਾਰਿਤ": "the (ਖ਼ਾਸ ਚੀਜ਼ ਲਈ)\nਉਦਾਹਰਨ: ਸੂਰਜ ਚਮਕਦਾ ਹੈ।"
            },
            "Hindi": {
                "अनिश्चित (Indefinite)": "a, an (किसी भी चीज़ के लिए)\nउदाहरण: मैंने एक कुत्ता देखा।",
                "निश्चित (Definite)": "the (विशेष चीज़ के लिए)\nउदाहरण: सूरज चमक रहा है।"
            }
        },
        "Prepositions": {
            "English": {
                "Place": "in, on, under, between, behind",
                "Time": "at, on, in, since, for",
                "Direction/Movement": "to, from, into, onto"
            },
            "Punjabi": {
                "ਸਥਾਨ": "in, on, under, between, behind",
                "ਸਮਾਂ": "at, on, in, since, for",
                "ਦਿਸ਼ਾ/ਚਲਨ": "to, from, into, onto"
            },
            "Hindi": {
                "स्थान": "in, on, under, between, behind",
                "समय": "at, on, in, since, for",
                "दिशा/गति": "to, from, into, onto"
            }
        },
        "Conjunctions": {
            "English": {
                "Coordinating": "and, but, or, so",
                "Subordinating (basic)": "because, if, when"
            },
            "Punjabi": {
                "ਸਹਿ-ਸੰਯੋਜਕ": "and, but, or, so",
                "ਉਪ-ਸੰਯੋਜਕ (ਮੂਲ)": "because, if, when"
            },
            "Hindi": {
                "समन्वयकारी": "and, but, or, so",
                "अधीनकारी (मूल)": "because, if, when"
            }
        }
    }
    language = session.get('language', 'Punjabi')  # default mother tongue

    return render_template(
        'module3.html',
        data=module3_data,
        types=module3_types,
        language=language
    )
#----------module 4-------------------

QUESTIONS = [
    {
    "en": "I ______ to school every day.",
    "hi": "मैं हर दिन स्कूल ______ जाता हूँ।",
    "pa": "ਮੈਂ ਹਰ ਰੋਜ਼ ਸਕੂਲ ______ ਜਾਂਦਾ ਹਾਂ।",
    "options": ["go", "went", "going"],
    "answer": "go"
    },
    {
    "en": "She ______ reading a book now.",
    "hi": "वह अभी किताब ______ पढ़ रही है।",
    "pa": "ਉਹ ਹੁਣੇ ਕਿਤਾਬ ______ ਪੜ੍ਹ ਰਹੀ ਹੈ।",
    "options": ["is", "are", "am"],
    "answer": "is"
    },
    {
    "en": "They ______ dinner yesterday.",
    "hi": "उन्होंने कल रात का खाना ______।",
    "pa": "ਉਨ੍ਹਾਂ ਨੇ ਕੱਲ੍ਹ ਰਾਤ ਦਾ ਖਾਣਾ ______।",
    "options": ["eat", "ate", "eating"],
    "answer": "ate"
    },
    {
    "en":"I ______ help you tomorrow.",
    "hi":"मैं ______ आपकी मदद करूँगा।",
    "pa":"ਮੈਂ ਕੱਲ੍ਹ ਨੂੰ ਤੁਹਾਡੀ ______ ਮਦਦ ਕਰਾਂਗਾ।",
    "options":["will","did","am"],
    "answer":"will"
    },
    {
    "en":"He ______ playing football when it rained.",
    "hi":"जब ______ हुई तो वह फुटबॉल खेल रहा था।",
    "pa":"ਜਦੋਂ ਮੀਂਹ ਪਿਆ ਤਾਂ ਉਹ ______ ਫੁੱਟਬਾਲ ਖੇਡ ਰਿਹਾ ਸੀ।",
    "options":["was","is","will"],
    "answer":"was"
    },
     {
    "en": "I saw ___ dog in the park.",
    "hi": "मैंने पार्क में ___ कुत्ता देखा।",
    "pa": "ਮੈਂ ਪਾਰਕ ਵਿੱਚ ___ ਕੁੱਤਾ ਵੇਖਿਆ।",
    "options": ["a", "an", "the"],
    "answer": "a"
  },
  {
    "en": "___ sun rises in the east.",
    "hi": "___ सूरज पूरब में उगता है।",
    "pa": "___ ਸੂਰਜ ਪੂਰਬ ਵਿੱਚ ਚੜ੍ਹਦਾ ਹੈ।",
    "options": ["A", "An", "The"],
    "answer": "The"
  },
  {
    "en": "She bought ___ orange.",
    "hi": "उसने ___ संतरा खरीदा।",
    "pa": "ਉਸਨੇ ___ ਸੰਤਰਾ ਖਰੀਦਿਆ।",
    "options": ["a", "an", "the"],
    "answer": "an"
  },
  {
    "en": "I have ___ book in my bag.",
    "hi": "मेरे बैग में ___ किताब है।",
    "pa": "ਮੇਰੇ ਬੈਗ ਵਿੱਚ ___ ਕਿਤਾਬ ਹੈ।",
    "options": ["a", "an", "the"],
    "answer": "a"
  },
  {
    "en": "___ moon looks beautiful tonight.",
    "hi": "आज रात ___ चाँद सुंदर लग रहा है।",
    "pa": "ਅੱਜ ਰਾਤ ___ ਚੰਨ ਸੁੰਦਰ ਲੱਗ ਰਿਹਾ ਹੈ।",
    "options": ["The", "A", "An"],
    "answer": "The"
  },
  {
    "en": "Ravi is my friend. → ___ is my friend.",
    "hi": "रवि मेरा दोस्त है। → ___ मेरा दोस्त है।",
    "pa": "ਰਵੀ ਮੇਰਾ ਦੋਸਤ ਹੈ। → ___ ਮੇਰਾ ਦੋਸਤ ਹੈ।",
    "options": ["He", "Him", "They"],
    "answer": "He"
  },
  {
    "en": "Give the book to Sita. → Give the book to ___.",
    "hi": "पुस्तक सीता को दो। → पुस्तक ___ को दो।",
    "pa": "ਕਿਤਾਬ ਸੀਤਾ ਨੂੰ ਦੇ। → ਕਿਤਾਬ ___ ਨੂੰ ਦੇ।",
    "options": ["she", "her", "him"],
    "answer": "her"
  },
  {
    "en": "This is my bag. That is ___ bag.",
    "hi": "यह मेरा बैग है। वह ___ बैग है।",
    "pa": "ਇਹ ਮੇਰਾ ਬੈਗ ਹੈ। ਉਹ ___ ਬੈਗ ਹੈ।",
    "options": ["my", "her", "his"],
    "answer": "her"
  },
  {
    "en": "I am going to market. → ___ am going to market.",
    "hi": "मैं बाजार जा रहा हूँ। → ___ बाजार जा रहा हूँ।",
    "pa": "ਮੈਂ ਬਾਜ਼ਾਰ ਜਾ ਰਿਹਾ ਹਾਂ। → ___ ਬਾਜ਼ਾਰ ਜਾ ਰਿਹਾ ਹਾਂ।",
    "options": ["I", "Me", "He"],
    "answer": "I"
  },
  {
    "en": "They are playing football. → I see ___.",
    "hi": "वे फुटबॉल खेल रहे हैं। → मैं ___ देख रहा हूँ।",
    "pa": "ਉਹ ਫੁੱਟਬਾਲ ਖੇਡ ਰਹੇ ਹਨ। → ਮੈਂ ___ ਵੇਖ ਰਿਹਾ ਹਾਂ।",
    "options": ["they", "them", "their"],
    "answer": "them"
  },
  {
    "en": "The book is ___ the table.",
    "hi": "किताब मेज ___ है।",
    "pa": "ਕਿਤਾਬ ਮੇਜ਼ ___ ਹੈ।",
    "options": ["on", "in", "under"],
    "answer": "on"
  },
  {
    "en": "I will meet you ___ Monday.",
    "hi": "मैं तुमसे ___ सोमवार को मिलूँगा।",
    "pa": "ਮੈਂ ਤੁਹਾਨੂੰ ___ ਸੋਮਵਾਰ ਨੂੰ ਮਿਲਾਂਗਾ।",
    "options": ["on", "in", "at"],
    "answer": "on"
  },
  {
    "en": "The cat is hiding ___ the box.",
    "hi": "बिल्ली डिब्बे ___ छुपी है।",
    "pa": "ਬਿੱਲੀ ਡੱਬੇ ___ ਲੁਕ ਰਹੀ ਹੈ।",
    "options": ["under", "on", "in"],
    "answer": "under"
  },
  {
    "en": "He is going ___ the market.",
    "hi": "वह बाजार ___ जा रहा है।",
    "pa": "ਉਹ ਬਾਜ਼ਾਰ ___ ਜਾ ਰਿਹਾ ਹੈ।",
    "options": ["to", "from", "by"],
    "answer": "to"
  },
  {
    "en": "The shop is ___ the school and the park.",
    "hi": "दुकान स्कूल और पार्क ___ है।",
    "pa": "ਦੁਕਾਨ ਸਕੂਲ ਅਤੇ ਪਾਰਕ ___ ਹੈ।",
    "options": ["between", "under", "on"],
    "answer": "between"
  },
  {
    "en": "I like tea ___ coffee.",
    "hi": "मुझे चाय ___ कॉफ़ी पसंद है।",
    "pa": "ਮੈਨੂੰ ਚਾਹ ___ ਕੌਫ਼ੀ ਪਸੰਦ ਹੈ।",
    "options": ["and", "but", "so"],
    "answer": "and"
  },
  {
    "en": "She is small ___ strong.",
    "hi": "वह छोटी ___ मज़बूत है।",
    "pa": "ਉਹ ਛੋਟੀ ___ ਮਜ਼ਬੂਤ ਹੈ।",
    "options": ["and", "or", "because"],
    "answer": "and"
  },
  {
    "en": "I am tired, ___ I will rest.",
    "hi": "मैं थका हुआ हूँ, ___ मैं आराम करूँगा।",
    "pa": "ਮੈਂ ਥੱਕਿਆ ਹੋਇਆ ਹਾਂ, ___ ਮੈਂ ਆਰਾਮ ਕਰਾਂਗਾ।",
    "options": ["so", "but", "and"],
    "answer": "so"
  },
  {
    "en": "I cannot come ___ I am busy.",
    "hi": "मैं नहीं आ सकता ___ मैं व्यस्त हूँ।",
    "pa": "ਮੈਂ ਨਹੀਂ ਆ ਸਕਦਾ ___ ਮੈਂ ਵਿਅਸਤ ਹਾਂ।",
    "options": ["because", "and", "or"],
    "answer": "because"
  },
  {
    "en": "You can have tea ___ coffee.",
    "hi": "तुम चाय ___ कॉफ़ी ले सकते हो।",
    "pa": "ਤੁਸੀਂ ਚਾਹ ___ ਕੌਫ਼ੀ ਲੈ ਸਕਦੇ ਹੋ।",
    "options": ["and", "or", "so"],
    "answer": "or"
  }
]
@app.route('/module4')
def module4():
    if 'loggedin' not in session:
        return require_login_redirect()

    # map stored user language to short code
    user_lang = session.get('language', 'English') or 'English'
    lang_map = {'english': 'en', 'hindi': 'hi', 'punjabi': 'pa'}
    session['lang'] = lang_map.get(user_lang.strip().lower(), 'hi')  # default Hindi

    # initialize quiz state
    session['current'] = 0
    session['score'] = 0

    return redirect(url_for('question'))

@app.route('/question', methods=['GET', 'POST'])
def question():
    if 'loggedin' not in session:
        return require_login_redirect()

    current = session.get('current', 0)
    lang = session.get('lang', 'hi')

    if request.method == 'POST':
        selected = request.form.get('option')
        if selected == QUESTIONS[current]["answer"]:
            session['score'] += 1
        session['current'] += 1
        current = session['current']
        if current >= len(QUESTIONS):
            return redirect(url_for('result'))

    q = QUESTIONS[current]
    return render_template(
        'module4.html',
        question_en=q['en'],
        question_local=q[lang],
        options=q['options'],
        q_no=current + 1,
        total=len(QUESTIONS)
    )

@app.route('/result')
def result():
    if 'loggedin' not in session:
        return require_login_redirect()

    score = session.get('score', 0)
    total = len(QUESTIONS)
    return render_template('result.html', score=score, total=total)
#----------------module 5---------------
level1_questions = [
    {"en": "This is an English course.", "hi": "यह एक अंग्रेज़ी कोर्स है।", "pa": "ਇਹ ਇੱਕ ਅੰਗ੍ਰੇਜ਼ੀ ਕੋਰਸ ਹੈ।", "options": ["True", "False"], "answer": "True"},
    {"en": "There are three classes every week.", "hi": "हर हफ़्ते तीन कक्षाएं होती हैं।", "pa": "ਹਰ ਹਫ਼ਤੇ ਤਿੰਨ ਕਲਾਸਾਂ ਹੁੰਦੀਆਂ ਹਨ।", "options": ["True", "False"], "answer": "False"},
    {"en": "The class begins in May.", "hi": "कक्षा मई में शुरू होती है।", "pa": "ਕਲਾਸ ਮਈ ਵਿੱਚ ਸ਼ੁਰੂ ਹੁੰਦੀ ਹੈ।", "options": ["True", "False"], "answer": "False"},
    {"en": "There is a book for the course.", "hi": "कोर्स के लिए एक पुस्तक है।", "pa": "ਕੋਰਸ ਲਈ ਇੱਕ ਕਿਤਾਬ ਹੈ।", "options": ["True", "False"], "answer": "True"},
    {"en": "The students need the teacher's book.", "hi": "छात्रों को शिक्षक की पुस्तक की आवश्यकता है।", "pa": "ਵਿਦਿਆਰਥੀਆਂ ਨੂੰ ਅਧਿਆਪਕ ਦੀ ਕਿਤਾਬ ਦੀ ਲੋੜ ਹੈ।", "options": ["True", "False"], "answer": "False"},
    {"en": "Photocopies of the book are not allowed.", "hi": "पुस्तक की प्रतियां अनुमति नहीं हैं।", "pa": "ਕਿਤਾਬ ਦੀ ਫੋਟੋਕਾਪੀ ਦੀ ਆਗਿਆ ਨਹੀਂ ਹੈ।", "options": ["True", "False"], "answer": "True"},
    {"en": "The first class is next Monday.", "hi": "पहली कक्षा अगले सोमवार है।", "pa": "ਪਹਿਲੀ ਕਲਾਸ ਅਗਲੇ ਸੋਮਵਾਰ ਨੂੰ ਹੈ।", "options": ["True", "False"], "answer": "True"},
    {"en": "The next class is on Tuesday.", "hi": "अगली कक्षा मंगलवार को है।", "pa": "ਅਗਲੀ ਕਲਾਸ ਮੰਗਲਵਾਰ ਨੂੰ ਹੈ।", "options": ["True", "False"], "answer": "False"}
]

level2_questions = [
    {"en": "What is the teacher's name?", "hi": "शिक्षक का नाम क्या है?", "pa": "ਅਧਿਆਪਕ ਦਾ ਨਾਮ ਕੀ ਹੈ?", "options": ["Lindsay Black", "Lindsey Black", "Linsey Black"], "answer": "Lindsay Black"},
    {"en": "What room is the class in?", "hi": "कक्षा किस कमरे में है?", "pa": "ਕਲਾਸ ਕਿਹੜੇ ਕਮਰੇ ਵਿੱਚ ਹੈ?", "options": ["Room 13", "Room 30", "Room 33"], "answer": "Room 13"},
    {"en": "What days is the class?", "hi": "कक्षा कौन से दिनों में होती है?", "pa": "ਕਲਾਸ ਕਿਹੜੇ ਦਿਨਾਂ ਵਿੱਚ ਹੁੰਦੀ ਹੈ?", "options": ["Monday and Tuesday", "Monday and Wednesday", "Monday and Thursday"], "answer": "Monday and Wednesday"},
    {"en": "How long is the class?", "hi": "कक्षा कितनी लंबी है?", "pa": "ਕਲਾਸ ਕਿੰਨੀ ਲੰਮੀ ਹੈ?", "options": ["One hour", "One hour and a half", "Two and a half hours"], "answer": "One hour and a half"},
    {"en": "When is the teacher's office hour?", "hi": "शिक्षक का कार्यालय समय कब है?", "pa": "ਅਧਿਆਪਕ ਦਾ ਦਫ਼ਤਰ ਕਦੋਂ ਹੈ?", "options": ["On Monday and Wednesday", "Room 7B", "Friday at 18.00"], "answer": "Friday at 18.00"},
    {"en": "What date does the course begin?", "hi": "कोर्स किस तारीख से शुरू होता है?", "pa": "ਕੋਰਸ ਕਿਹੜੀ ਤਾਰੀਖ ਤੋਂ ਸ਼ੁਰੂ ਹੁੰਦਾ ਹੈ?", "options": ["Monday 13 March", "Monday 30 March", "Monday 13 May"], "answer": "Monday 13 March"}
]

# ------------------ ROUTES ------------------
@app.route('/')
def home_page():
    return "<h1>Home Page</h1><p><a href='/module5'>Start Module 5 Quiz</a></p>"

@app.route('/module5')
def module5():
    if 'loggedin' not in session:
        return require_login_redirect()

    # Determine mother language: Hindi => show Hindi, else Punjabi
    mother_lang = session.get('language', 'English').lower()
    session['lang'] = 'hi' if mother_lang == 'hindi' else 'pa'
    
    session['current'] = 0
    session['score'] = 0
    return render_template('module5.html', start_audio=True)

@app.route('/module5/question', methods=['POST'])
def module5_question():
    all_questions = level1_questions + level2_questions
    current = session.get('current', 0)
    lang = session.get('lang', 'pa')

    selected = request.form.get('option')
    if selected:  # Only increment if user answered
        if selected == all_questions[current]["answer"]:
            session['score'] += 1
        session['current'] += 1
        current = session['current']
        if current >= len(all_questions):
            return redirect(url_for('module5_result2'))

    q = all_questions[current]
    return render_template(
        'module5.html',
        start_audio=False,
        question_en=q['en'],
        question_local=q.get(lang, q['en']),
        options=q['options'],
        q_no=current + 1,
        total=len(all_questions)
    )

@app.route('/module5/result2')
def module5_result2():
    score = session.get('score', 0)
    total = len(level1_questions + level2_questions)
    return render_template('result2.html', score=score, total=total)

#--------------MAIN-----------------
if __name__ == "__main__":
    # optionally print which features are enabled:
    print("TTS enabled:", engine is not None)
    app.run(host="0.0.0.0", port=5000, debug=True)
