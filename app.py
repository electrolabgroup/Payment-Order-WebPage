from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
import requests
import pandas as pd
from datetime import datetime, timedelta
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
import re
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2 import Error

random_number = random.randint(14364546454654654654651465654, 9168468484867187618761871687171)

app = Flask(__name__)
app.secret_key = str(random_number)

DB_CONFIG = {
    'host': 'localhost',
    # 'host' :'192.168.2.11',
    'port': 5432,
    'database': 'postgres',
    'user': 'postgres',
    'password': 'admin@123'
}

SMTP_SERVER = "email.electrolabgroup.com"
SMTP_PORT = 587
SMTP_USERNAME = "econnect"
SMTP_PASSWORD = "Requ!reMent$"

def init_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS Email_Users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
    except (Exception, Error) as error:
        print("Error while connecting to PostgreSQL", error)
    finally:
        if conn:
            cur.close()
            conn.close()

BASE_URL = 'https://erpv14.electrolabgroup.com/'
API_ENDPOINT = 'api/resource/Payment Order'
API_HEADERS = {
    'Authorization': 'token 3ee8d03949516d0:6baa361266cf807',
    'Content-Type': 'application/json'
}

def update_verifier_status(order_name):
    """Update verifier status for a specific payment order"""
    url = f"{BASE_URL}{API_ENDPOINT}/{order_name}"
    
    payload = {
        "custom_verifier_1": 1,
        "custom_verifier_2": 1
    }   
    
    try:
        response = requests.put(url, headers=API_HEADERS, data=json.dumps(payload))
        if response.status_code == 200:
            print(f"Successfully updated verifier status for {order_name}")
            return True
        else:
            print(f"Failed to update verifier status for {order_name}. Status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error updating verifier status: {e}")
        return False

def send_otp_email(otp, order_name, recipient_email):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = recipient_email
        msg['Subject'] = "OTP Notification"
        
        message = f"Your OTP for Payment Entry {order_name} is {otp}"
        msg.attach(MIMEText(message, 'plain'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_USERNAME, [recipient_email], msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def fetch_payment_data():
    url = BASE_URL + API_ENDPOINT
    params = {
        'fields': '["name","company","payment_order_type","company_bank_account","company_bank","posting_date","account","references.reference_name","references.reference_doctype","references.amount","references.supplier","custom_verifier_1","custom_verifier_2"]',
        'limit_start': 0,
        'limit_page_length': 100000000000,
    }
    
    response = requests.get(url, params=params, headers=API_HEADERS)
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data['data'])
        df['posting_date'] = pd.to_datetime(df['posting_date'])
        df['custom_verifier_1'] = df['custom_verifier_1'].replace(0,"No")
        df['custom_verifier_1'] = df['custom_verifier_1'].replace(1,"Yes")
        df['custom_verifier_2'] = df['custom_verifier_2'].replace(0,"No")
        df['custom_verifier_2'] = df['custom_verifier_2'].replace(1,"Yes")
        return df
    return None

@app.route('/')
def root():
    if 'user_email' in session:
        return redirect(url_for('search'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            
            cur.execute('SELECT * FROM Email_Users WHERE email = %s', (email,))
            user = cur.fetchone()
            
            if user and check_password_hash(user[2], password):
                session['user_email'] = email
                return redirect(url_for('search'))
            else:
                flash('Invalid email or password')
        except (Exception, Error) as error:
            print("Error while connecting to PostgreSQL", error)
            flash('An error occurred during login')
        finally:
            if conn:
                cur.close()
                conn.close()
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            
            cur.execute(
                'INSERT INTO Email_Users (email, password) VALUES (%s, %s)',
                (email, generate_password_hash(password))
            )
            conn.commit()
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            flash('Email already exists')
        except (Exception, Error) as error:
            print("Error while connecting to PostgreSQL", error)
            flash('An error occurred during registration')
        finally:
            if conn:
                cur.close()
                conn.close()
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('login'))

@app.route('/search', methods=['GET', 'POST'])
def search():
    if 'user_email' not in session:
        return redirect(url_for('login'))
        
    df = fetch_payment_data()
    search_results = None
    show_otp_form = False
    
    if request.method == 'POST':
        if 'search_term' in request.form:
            search_term = request.form.get('search_term', '').strip()
            if search_term and df is not None:
                search_results = df[df['name'].str.contains(search_term, case=False, na=False)]
                
                if not search_results.empty:
                    grouped_results = {}
                    for _, row in search_results.iterrows():
                        order_key = row['name']
                        if order_key not in grouped_results:
                            grouped_results[order_key] = {
                                'name': row['name'],
                                'posting_date': row['posting_date'],
                                'account': row['account'],
                                'company': row['company'],
                                'payment_order_type': row['payment_order_type'],
                                'company_bank_account': row['company_bank_account'],
                                'company_bank': row['company_bank'],
                                'custom_verifier_1': row['custom_verifier_1'],
                                'custom_verifier_2': row['custom_verifier_2'],
                                'references': []
                            }
                        grouped_results[order_key]['references'].append({
                            'reference_name': row['reference_name'],
                            'amount': row['amount'],
                            'supplier': row['supplier'],
                            'reference_doctype': row['reference_doctype']
                        })
                    search_results = list(grouped_results.values())
        
        elif 'send_otp' in request.form:
            order_name = request.form.get('order_name')
            otp = str(random.randint(100000, 999999))
            session['otp'] = otp
            session['order_name'] = order_name
            
            if send_otp_email(otp, order_name, session['user_email']):
                flash('OTP sent successfully! Please check your email.')
                show_otp_form = True
                if df is not None:
                    search_results = df[df['name'].str.contains(order_name, case=False, na=False)]
                    if not search_results.empty:
                        grouped_results = {}
                        for _, row in search_results.iterrows():
                            order_key = row['name']
                            if order_key not in grouped_results:
                                grouped_results[order_key] = {
                                    'name': row['name'],
                                    'posting_date': row['posting_date'],
                                    'account': row['account'],
                                    'company': row['company'],
                                    'payment_order_type': row['payment_order_type'],
                                    'company_bank_account': row['company_bank_account'],
                                    'company_bank': row['company_bank'],
                                    'custom_verifier_1': row['custom_verifier_1'],
                                    'custom_verifier_2': row['custom_verifier_2'],
                                    'references': []
                                }
                            grouped_results[order_key]['references'].append({
                                'reference_name': row['reference_name'],
                                'amount': row['amount'],
                                'supplier': row['supplier'],
                                'reference_doctype': row['reference_doctype']
                            })
                        search_results = list(grouped_results.values())
            else:
                flash('Failed to send OTP. Please try again.')

        elif 'verify_otp' in request.form:
            entered_otp = request.form.get('otp')
            if entered_otp == session.get('otp'):
                order_name = session.get('order_name')
                
                if update_verifier_status(order_name):
                    session.pop('otp', None)
                    session.pop('order_name', None)
                    flash('Verification status updated successfully!')
                    return render_template('success.html', order_name=order_name)
                else:
                    flash('Failed to update verification status. Please try again.')
                    show_otp_form = True
            else:
                flash('Invalid OTP. Please try again.')
                show_otp_form = True
                order_name = session.get('order_name')
                if df is not None and order_name:
                    search_results = df[df['name'].str.contains(order_name, case=False, na=False)]
                    if not search_results.empty:
                        grouped_results = {}
                        for _, row in search_results.iterrows():
                            order_key = row['name']
                            if order_key not in grouped_results:
                                grouped_results[order_key] = {
                                    'name': row['name'],
                                    'posting_date': row['posting_date'],
                                    'account': row['account'],
                                    'company': row['company'],
                                    'payment_order_type': row['payment_order_type'],
                                    'company_bank_account': row['company_bank_account'],
                                    'company_bank': row['company_bank'],
                                    'custom_verifier_1': row['custom_verifier_1'],
                                    'custom_verifier_2': row['custom_verifier_2'],
                                    'references': []
                                }
                            grouped_results[order_key]['references'].append({
                                'reference_name': row['reference_name'],
                                'amount': row['amount'],
                                'supplier': row['supplier'],
                                'reference_doctype': row['reference_doctype']
                            })
                        search_results = list(grouped_results.values())
    
    return render_template('search.html', search_results=search_results, show_otp_form=show_otp_form)

@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    if 'user_email' not in session:
        return jsonify([])
        
    search_term = request.args.get('search_term', '').strip()
    if search_term:
        df = fetch_payment_data()
        if df is not None:
            pattern = re.escape(search_term)
            matching_rows = df[df['name'].str.contains(pattern, case=False, na=False)]

            suggestions = [
                f"<strong>Name - {row['name']}</strong><br>Account - {row['account']} "
                for _, row in matching_rows.iterrows()
            ]

            unique_suggestions = list(dict.fromkeys(suggestions))[:4]
            return jsonify(unique_suggestions)
    return jsonify([])

if __name__ == '__main__':
    init_db() 
    # app.run(debug=True)
    app.run(host = '0.0.0.0', port = 8000, debug=True)
