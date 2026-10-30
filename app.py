from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, FLASK_SECRET_KEY, SENDGRID_API_KEY, SENDGRID_FROM_EMAIL
from functools import wraps
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os, random, string, math
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ══════════════════════════════════════
# GLOBAL VARIABLES FOR ALL HTML TEMPLATES
# ══════════════════════════════════════
@app.context_processor
def inject_globals():
    return {
        'user': session.get('user'),
        'customer': session.get('customer')
    }

# ══════════════════════════════════════
# AUTH DECORATORS
# ══════════════════════════════════════
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def customer_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'customer' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════
# HELPER FUNCTIONS (Email)
# ══════════════════════════════════════
def send_email(to_email, subject, html_content):
    try:
        if not SENDGRID_API_KEY: return
        sg  = SendGridAPIClient(SENDGRID_API_KEY)
        msg = Mail(
            from_email=SENDGRID_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sg.send(msg)
    except Exception as e:
        print(f"Email error: {e}")

def send_booking_confirmation(customer_email, customer_name, booking_ref, vehicle_name, start_date, end_date, amount):
    send_email(
        customer_email,
        f'Booking Confirmed — {booking_ref}',
        f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;">
          <h2 style="color:#2563eb;">QuickRent</h2>
          <p>Hi {customer_name},</p>
          <p>Your booking is confirmed!</p>
          <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr><td style="padding:8px;color:#666;">Booking Ref</td><td style="padding:8px;font-weight:bold;">{booking_ref}</td></tr>
            <tr><td style="padding:8px;color:#666;">Vehicle</td><td style="padding:8px;">{vehicle_name}</td></tr>
            <tr><td style="padding:8px;color:#666;">Pick Up</td><td style="padding:8px;">{start_date}</td></tr>
            <tr><td style="padding:8px;color:#666;">Return</td><td style="padding:8px;">{end_date}</td></tr>
            <tr><td style="padding:8px;color:#666;">Total</td><td style="padding:8px;color:#2563eb;font-weight:bold;">₹{amount:,}</td></tr>
          </table>
          <p style="color:#666;font-size:12px;">— QuickRent Team</p>
        </div>"""
    )

# ══════════════════════════════════════
# UNIFIED LOGIN (ADMIN & CUSTOMER)
# ══════════════════════════════════════
@app.route('/login', methods=['GET', 'POST'])
@app.route('/customer/login', methods=['GET', 'POST'])
def login():
    if 'user' in session and request.path == '/login':
        return redirect(url_for('dashboard'))
    if 'customer' in session and request.path == '/customer/login':
        return redirect(url_for('customer_dashboard'))

    error = None
    if request.method == 'POST':
        session.clear()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        try:
            response = db.auth.sign_in_with_password({'email': email, 'password': password})
            user_id = response.user.id
            profile = db.table('profiles').select('*').eq('id', user_id).execute()
            
            if not profile.data:
                error = 'Profile not found. Please contact support.'
            else:
                role = profile.data[0]['role']
                
                # ADMIN LOGIN
                if role in ['admin', 'owner']:
                    session['user'] = {'id': user_id, 'email': email}
                    session['access_token'] = response.session.access_token
                    return redirect(url_for('dashboard'))
                    
                # CUSTOMER LOGIN
                elif role == 'customer':
                    customer_id = profile.data[0]['customer_id']
                    customer = db.table('customers').select('*').eq('id', customer_id).execute()
                    
                    if customer.data:
                        session['customer'] = {
                            'id': customer_id,
                            'user_id': user_id,
                            'name': customer.data[0]['name'],
                            'email': customer.data[0]['email']
                        }
                        return redirect(url_for('customer_dashboard'))
                    else:
                        error = 'Customer record missing.'
        except Exception as e:
            error = 'Invalid email or password. Please try again.'

    template = 'customer/login.html' if request.path == '/customer/login' else 'login.html'
    return render_template(template, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ══════════════════════════════════════
# CUSTOMER REGISTER & LOGOUT
# ══════════════════════════════════════
@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    if 'customer' in session: return redirect(url_for('customer_dashboard'))

    error, success = None, None
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip()
        phone    = request.form.get('phone', '').strip()
        city     = request.form.get('city', '').strip()
        password = request.form.get('password', '').strip()
        confirm  = request.form.get('confirm', '').strip()

        if not all([name, email, password, confirm]):
            error = 'Name, email and password are required.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        else:
            try:
                auth_response = db.auth.sign_up({'email': email, 'password': password})
                user_id = auth_response.user.id

                customer_res = db.table('customers').insert({
                    'name': name, 'email': email, 'phone': phone, 'city': city,
                    'total_rentals': 0, 'total_spent': 0
                }).execute()
                customer_id = customer_res.data[0]['id']

                db.table('profiles').insert({
                    'id': user_id, 'role': 'customer', 'customer_id': customer_id
                }).execute()

                success = 'Account created successfully. You can now log in.'
            except Exception as e:
                error_msg = str(e)
                if 'already registered' in error_msg or 'already exists' in error_msg:
                    error = 'An account with this email already exists.'
                else:
                    error = 'Registration failed. Please try again.'

    return render_template('customer/register.html', error=error, success=success)

@app.route('/customer/logout')
def customer_logout():
    session.pop('customer', None)
    return redirect(url_for('login'))

# ══════════════════════════════════════
# SIDEBAR COMPONENT
# ══════════════════════════════════════
@app.route('/components/sidebar')
@login_required
def sidebar_component():
    return render_template('components/sidebar.html')

# ══════════════════════════════════════
# ADMIN PORTAL PAGES
# ══════════════════════════════════════
@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    try:
        current_month = datetime.now().strftime('%Y-%m')
        # Fetch status-only rows once per collection instead of making seven
        # sequential count requests to Supabase for the dashboard cards.
        vehicles_res = db.table('vehicles').select('status').execute()
        booking_statuses = db.table('bookings').select('status').execute()
        vehicle_statuses = [v.get('status') for v in (vehicles_res.data or [])]
        booking_statuses = [b.get('status') for b in (booking_statuses.data or [])]

        recent_bookings = db.table('bookings')\
            .select('*, customers(name), vehicles(name, type)')\
            .order('created_at', desc=True).limit(5).execute()

        payments_res = db.table('payments').select('amount, status, created_at').execute()
        total_revenue = sum(p['amount'] for p in payments_res.data if p['status'] == 'paid') if payments_res.data else 0
        monthly_revenue = sum(
            p['amount'] for p in payments_res.data
            if p['status'] == 'paid' and p.get('created_at', '')[:7] == current_month
        ) if payments_res.data else 0

        return render_template('dashboard.html',
            total_vehicles=len(vehicle_statuses), total_revenue=total_revenue, monthly_revenue=monthly_revenue,
            available_vehicles=vehicle_statuses.count('available'), rented_vehicles=vehicle_statuses.count('rented'), maintenance_vehicles=vehicle_statuses.count('maintenance'),
            active_bookings=booking_statuses.count('active'), pending_bookings=booking_statuses.count('pending'), overdue_bookings=booking_statuses.count('overdue'),
            recent_bookings=recent_bookings.data or []
        )
    except Exception as e:
        print('Dashboard error:', e)
        return render_template('dashboard.html')

@app.route('/bookings')
@login_required
def bookings():
    try:
        status_filter = request.args.get('status', 'all')
        query = db.table('bookings').select('*, customers(name, phone), vehicles(name, type)').order('created_at', desc=True)
        if status_filter != 'all': query = query.eq('status', status_filter)
        bookings_res = query.execute()

        statuses = db.table('bookings').select('status').execute()
        status_values = [booking.get('status') for booking in (statuses.data or [])]
        counts = {key: status_values.count(key) for key in ('active', 'pending', 'overdue', 'completed')}
        counts['all'] = len(status_values)
        return render_template('bookings.html', bookings=bookings_res.data or [], counts=counts, active_filter=status_filter)
    except Exception as e:
        return render_template('bookings.html')

@app.route('/vehicles')
@login_required
def vehicles():
    try:
        type_filter = request.args.get('type', 'all')
        query = db.table('vehicles').select('*').order('created_at', desc=True)
        if type_filter in ['car', 'bike']: query = query.eq('type', type_filter)
        elif type_filter == 'unavailable': query = query.neq('status', 'available')
        vehicles_res = query.execute()
        return render_template('vehicles.html', vehicles=vehicles_res.data or [], active_filter=type_filter)
    except Exception as e:
        return render_template('vehicles.html')

@app.route('/customers')
@login_required
def customers():
    try:
        customers_res = db.table('customers').select('*').order('created_at', desc=True).execute()
        counts = {'total': len(customers_res.data or [])}
        return render_template('customers.html', customers=customers_res.data or [], counts=counts)
    except Exception as e:
        return render_template('customers.html')

@app.route('/payments')
@login_required
def payments():
    try:
        status_filter = request.args.get('status', 'all')
        query = db.table('payments').select('*, bookings(booking_ref), customers(name)').order('created_at', desc=True)
        if status_filter != 'all': query = query.eq('status', status_filter)
        payments_res = query.execute()

        all_payments = db.table('payments').select('amount, status').execute()
        total_collected = sum(p['amount'] for p in all_payments.data if p['status'] == 'paid') if all_payments.data else 0
        total_pending = sum(p['amount'] for p in all_payments.data if p['status'] == 'pending') if all_payments.data else 0

        return render_template('payments.html', payments=payments_res.data or [], active_filter=status_filter, total_collected=total_collected, total_pending=total_pending)
    except Exception as e:
        return render_template('payments.html')

@app.route('/analytics')
@login_required
def analytics():
    try:
        vehicles_res = db.table('vehicles').select('*').execute()
        bookings_res = db.table('bookings').select('status, vehicles(type)').execute()
        customers_res = db.table('customers').select('*').execute()
        payments_res = db.table('payments').select('amount, status, created_at').execute()

        total_revenue = sum(p['amount'] for p in payments_res.data if p['status'] == 'paid') if payments_res.data else 0

        monthly = {}
        for p in (payments_res.data or []):
            if p['status'] == 'paid' and p.get('created_at'):
                month = p['created_at'][:7]
                monthly[month] = monthly.get(month, 0) + p['amount']

        sorted_months = sorted(monthly.keys())
        chart_labels = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in sorted_months]
        chart_data = [monthly[m] for m in sorted_months]

        all_bookings = bookings_res.data or []
        type_counts = {'car': 0, 'bike': 0, 'scooter': 0}
        for b in all_bookings:
            if b.get('vehicles') and b['vehicles'].get('type'):
                t = b['vehicles']['type']
                type_counts[t] = type_counts.get(t, 0) + 1

        avg_booking = int(total_revenue / len(all_bookings)) if all_bookings else 0

        return render_template('analytics.html', total_revenue=total_revenue, total_bookings=len(all_bookings), total_vehicles=len(vehicles_res.data or []), total_customers=len(customers_res.data or []), avg_booking=avg_booking, chart_labels=chart_labels, chart_data=chart_data, type_car=type_counts['car'], type_bike=type_counts['bike'], type_scooter=type_counts['scooter'])
    except Exception as e:
        return render_template('analytics.html')

@app.route('/rentals')
@login_required
def rentals():
    try:
        active = db.table('bookings').select('*, vehicles(name, type), customers(name)').in_('status', ['active', 'pending']).order('created_at', desc=True).execute()
        past = db.table('bookings').select('*, vehicles(name, type), customers(name)').in_('status', ['completed', 'overdue']).order('created_at', desc=True).execute()
        return render_template('rentals.html', active_rentals=active.data or [], past_rentals=past.data or [])
    except Exception as e:
        return render_template('rentals.html')

@app.route('/settings')
@login_required
def settings(): return render_template('settings.html')

@app.route('/notifications')
@login_required
def notifications(): return render_template('notifications.html')

@app.route('/help')
@login_required
def help_page(): return render_template('help.html')

# ══════════════════════════════════════
# ADMIN API ROUTES
# ══════════════════════════════════════
def vehicle_coordinates(data):
    latitude, longitude = data.get('latitude'), data.get('longitude')
    if latitude in ('', None) and longitude in ('', None):
        return None, None
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise ValueError('Enter both valid pickup coordinates, or leave both blank.')
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError('Pickup coordinates are outside the valid range.')
    return latitude, longitude

@app.route('/api/vehicles/add', methods=['POST'])
@login_required
def add_vehicle():
    data = request.get_json(silent=True) or {}
    try:
        if not data.get('name') or data.get('type') not in ('car', 'bike', 'scooter'):
            raise ValueError('Enter a vehicle name and valid type.')
        latitude, longitude = vehicle_coordinates(data)
        tier = data.get('tier', 'regular')
        body_style = data.get('body_style') or {'car': 'sedan', 'bike': 'motorcycle', 'scooter': 'scooter'}[data['type']]
        valid_styles = {'car': ('suv', 'sedan', 'hatchback'), 'bike': ('motorcycle',), 'scooter': ('scooter',)}
        if tier not in ('regular', 'premium') or body_style not in valid_styles[data['type']]:
            raise ValueError('Choose a valid vehicle class and body style.')
        result = db.table('vehicles').insert({
            'name': data['name'], 'type': data['type'], 'brand': data.get('brand', ''),
            'year': data.get('year'), 'fuel': data.get('fuel', 'Petrol'),
            'daily_rate': data['daily_rate'], 'status': 'available',
            'latitude': latitude, 'longitude': longitude, 'tier': tier, 'body_style': body_style
        }).execute()
        return jsonify({'success': True, 'vehicle': result.data})
    except (KeyError, ValueError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/customers/add', methods=['POST'])
@login_required
def add_customer():
    data = request.json
    result = db.table('customers').insert({
        'name': data['name'], 'email': data['email'], 'phone': data.get('phone', ''), 'city': data.get('city', '')
    }).execute()
    return jsonify({'success': True, 'customer': result.data})

@app.route('/api/customers/create-with-password', methods=['POST'])
@login_required
def create_customer_with_password():
    data = request.json
    if not data.get('password') or len(data['password']) < 8: return jsonify({'success': False, 'error': 'Password must be at least 8 characters'})
    try:
        auth_response = db.auth.sign_up({'email': data['email'], 'password': data['password']})
        customer_res = db.table('customers').insert({'name': data['name'], 'email': data['email'], 'phone': data.get('phone', ''), 'city': data.get('city', ''), 'total_rentals': 0, 'total_spent': 0}).execute()
        db.table('profiles').insert({'id': auth_response.user.id, 'role': 'customer', 'customer_id': customer_res.data[0]['id']}).execute()
        return jsonify({'success': True, 'customer': customer_res.data[0]})
    except Exception as e:
        return jsonify({'success': False, 'error': 'Account exists or database error.'})

@app.route('/api/bookings/add', methods=['POST'])
@login_required
def add_booking():
    data = request.json
    ref = 'BK-' + ''.join(random.choices(string.digits, k=4))
    result = db.table('bookings').insert({
        'booking_ref': ref, 'customer_id': data['customer_id'], 'vehicle_id': data['vehicle_id'],
        'start_date': data['start_date'], 'end_date': data['end_date'], 'total_amount': data['total_amount'],
        'status': 'pending', 'payment_status': 'pending'
    }).execute()
    db.table('vehicles').update({'status': 'rented'}).eq('id', data['vehicle_id']).execute()
    return jsonify({'success': True, 'booking': result.data})

@app.route('/api/payments/add', methods=['POST'])
@login_required
def add_payment():
    try:
        data = request.json
        ref = '#TXN-' + ''.join(random.choices(string.digits, k=4))
        cust_id = data.get('customer_id') if data.get('customer_id') != '' else None
        result = db.table('payments').insert({
            'transaction_ref': ref, 'booking_id': data['booking_id'], 'customer_id': cust_id,
            'amount': data['amount'], 'method': data['method'], 'status': 'paid'
        }).execute()
        db.table('bookings').update({'payment_status': 'paid', 'payment_method': data['method']}).eq('id', data['booking_id']).execute()
        return jsonify({'success': True, 'payment': result.data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customers/list')
@login_required
def list_customers():
    res = db.table('customers').select('id, name').order('name').execute()
    return jsonify({'customers': res.data or []})

@app.route('/api/vehicles/list')
@login_required
def list_vehicles():
    res = db.table('vehicles').select('id, name, type, daily_rate').eq('status', 'available').order('name').execute()
    return jsonify({'vehicles': res.data or []})

@app.route('/api/vehicles/<vehicle_id>', methods=['GET'])
@login_required
def get_vehicle(vehicle_id):
    res = db.table('vehicles').select('*').eq('id', vehicle_id).execute()
    return jsonify({'vehicle': res.data[0]}) if res.data else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/vehicles/<vehicle_id>/update', methods=['POST'])
@login_required
def update_vehicle(vehicle_id):
    data = request.get_json(silent=True) or {}
    try:
        if not data.get('name') or data.get('type') not in ('car', 'bike', 'scooter') or data.get('status') not in ('available', 'rented', 'maintenance'):
            raise ValueError('Enter a vehicle name, type, and valid status.')
        latitude, longitude = vehicle_coordinates(data)
        tier = data.get('tier', 'regular')
        body_style = data.get('body_style') or {'car': 'sedan', 'bike': 'motorcycle', 'scooter': 'scooter'}[data['type']]
        valid_styles = {'car': ('suv', 'sedan', 'hatchback'), 'bike': ('motorcycle',), 'scooter': ('scooter',)}
        if tier not in ('regular', 'premium') or body_style not in valid_styles[data['type']]:
            raise ValueError('Choose a valid vehicle class and body style.')
        db.table('vehicles').update({'name': data['name'], 'type': data['type'], 'brand': data.get('brand', ''), 'year': data.get('year'), 'fuel': data.get('fuel', 'Petrol'), 'daily_rate': data['daily_rate'], 'status': data['status'], 'latitude': latitude, 'longitude': longitude, 'tier': tier, 'body_style': body_style}).eq('id', vehicle_id).execute()
        return jsonify({'success': True})
    except (KeyError, ValueError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/vehicles/<vehicle_id>/delete', methods=['POST'])
@login_required
def delete_vehicle(vehicle_id):
    db.table('bookings').update({'vehicle_id': None}).eq('vehicle_id', vehicle_id).execute()
    db.table('vehicles').delete().eq('id', vehicle_id).execute()
    return jsonify({'success': True})

@app.route('/api/customers/<customer_id>', methods=['GET'])
@login_required
def get_customer(customer_id):
    res = db.table('customers').select('*').eq('id', customer_id).execute()
    if not res.data: return jsonify({'error': 'Not found'}), 404
    bookings = db.table('bookings').select('*, vehicles(name, type)').eq('customer_id', customer_id).order('created_at', desc=True).execute()
    return jsonify({'customer': res.data[0], 'bookings': bookings.data or []})

@app.route('/api/customers/<customer_id>/update', methods=['POST'])
@login_required
def update_customer(customer_id):
    data = request.json
    db.table('customers').update({'name': data['name'], 'email': data['email'], 'phone': data.get('phone', ''), 'city': data.get('city', '')}).eq('id', customer_id).execute()
    return jsonify({'success': True})

@app.route('/api/customers/<customer_id>/delete', methods=['POST'])
@login_required
def delete_customer(customer_id):
    db.table('payments').delete().eq('customer_id', customer_id).execute()
    db.table('bookings').update({'customer_id': None}).eq('customer_id', customer_id).execute()
    db.table('customers').delete().eq('id', customer_id).execute()
    return jsonify({'success': True})

@app.route('/api/bookings/<booking_id>', methods=['GET'])
@login_required
def get_booking(booking_id):
    res = db.table('bookings').select('*, customers(name, phone), vehicles(name, type)').eq('id', booking_id).execute()
    return jsonify({'booking': res.data[0]}) if res.data else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/bookings/<booking_id>/status', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    new_status = request.json['status']
    db.table('bookings').update({'status': new_status}).eq('id', booking_id).execute()
    booking = db.table('bookings').select('vehicle_id').eq('id', booking_id).execute()
    if booking.data and booking.data[0].get('vehicle_id'):
        if new_status == 'completed': db.table('vehicles').update({'status': 'available'}).eq('id', booking.data[0]['vehicle_id']).execute()
        if new_status == 'active': db.table('vehicles').update({'status': 'rented'}).eq('id', booking.data[0]['vehicle_id']).execute()
    return jsonify({'success': True})

@app.route('/api/bookings/<booking_id>/delete', methods=['POST'])
@login_required
def delete_admin_booking(booking_id):
    booking = db.table('bookings').select('vehicle_id, status').eq('id', booking_id).execute()
    if booking.data and booking.data[0].get('vehicle_id') and booking.data[0]['status'] in ['active', 'pending']:
        db.table('vehicles').update({'status': 'available'}).eq('id', booking.data[0]['vehicle_id']).execute()
    db.table('payments').delete().eq('booking_id', booking_id).execute()
    db.table('bookings').delete().eq('id', booking_id).execute()
    return jsonify({'success': True})

# ══════════════════════════════════════
# CUSTOMER PORTAL PAGES
# ══════════════════════════════════════
@app.route('/customer/dashboard')
@customer_login_required
def customer_dashboard():
    try:
        customer_id = session['customer']['id']
        bookings = db.table('bookings').select('*, vehicles(name, type, daily_rate, brand, year)').eq('customer_id', customer_id).order('created_at', desc=True).execute()
        try:
            nearby_vehicles = db.table('vehicles').select('id, name, type, daily_rate, latitude, longitude').eq('status', 'available').execute()
            nearby_vehicles = nearby_vehicles.data or []
        except Exception:
            nearby_vehicles = []
        active_bookings = [b for b in (bookings.data or []) if b['status'] in ['active', 'pending']]
        past_bookings   = [b for b in (bookings.data or []) if b['status'] in ['completed', 'overdue', 'cancelled']]
        total_spent = sum(b['total_amount'] for b in (bookings.data or []) if b['status'] == 'completed')
        return render_template('customer/dashboard.html', active_bookings=active_bookings, past_bookings=past_bookings, total_spent=total_spent, total_bookings=len(bookings.data or []), nearby_vehicles=nearby_vehicles, current_page='home')
    except Exception as e:
        return render_template('customer/dashboard.html', active_bookings=[], past_bookings=[], total_spent=0, total_bookings=0, nearby_vehicles=[], current_page='home')

@app.route('/api/customer/nearby-shops')
@customer_login_required
def customer_nearby_shops():
    """Find mapped rental businesses near a browser-provided location.

    If the public map service is unavailable, return the closest geocoded
    QuickRent vehicles, then available inventory as a useful final fallback.
    """
    area = request.args.get('area', '').strip()[:140]
    lat = lng = None
    if request.args.get('lat') and request.args.get('lng'):
        try:
            lat, lng = float(request.args['lat']), float(request.args['lng'])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError('Coordinates are outside valid bounds')
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'The current location is invalid.'}), 400
    elif not area:
        return jsonify({'success': False, 'error': 'Share your location or enter a city, area, or landmark.'}), 400

    if area and (lat is None or lng is None):
        try:
            geocoded = requests.get('https://photon.komoot.io/api/', params={'q': area, 'limit': 1}, timeout=(1.5, 3), headers={'User-Agent': 'QuickRent/1.0 nearby-shop-search'})
            geocoded.raise_for_status()
            features = geocoded.json().get('features') or []
            if features:
                coords = features[0].get('geometry', {}).get('coordinates') or []
                if len(coords) >= 2:
                    lng, lat = float(coords[0]), float(coords[1])
        except (requests.RequestException, ValueError, TypeError):
            pass

    def distance_km(point_lat, point_lng):
        rad = math.pi / 180
        dlat, dlng = (point_lat - lat) * rad, (point_lng - lng) * rad
        h = math.sin(dlat / 2) ** 2 + math.cos(lat * rad) * math.cos(point_lat * rad) * math.sin(dlng / 2) ** 2
        return 6371 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0, 1 - h)))

    # Prefer Google's Places data when configured. Keep the credential on the
    # server (GOOGLE_MAPS_API_KEY); the browser only receives public place data.
    google_api_key = os.getenv('GOOGLE_MAPS_API_KEY', '').strip()
    if google_api_key:
        try:
            search_text = f'vehicle rental shops near {area}' if area else 'car and motorcycle rental shops'
            payload = {'textQuery': search_text, 'languageCode': 'en', 'maxResultCount': 10}
            if lat is not None and lng is not None:
                payload['locationBias'] = {'circle': {'center': {'latitude': lat, 'longitude': lng}, 'radius': 20000}}
            response = requests.post(
                'https://places.googleapis.com/v1/places:searchText', json=payload,
                headers={'X-Goog-Api-Key': google_api_key,
                         'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.location,places.googleMapsUri,places.rating,places.nationalPhoneNumber'},
                timeout=(2, 5),
            )
            response.raise_for_status()
            places = []
            for place in response.json().get('places', []):
                location = place.get('location') or {}
                point_lat, point_lng = location.get('latitude'), location.get('longitude')
                if point_lat is None or point_lng is None:
                    continue
                point_lat, point_lng = float(point_lat), float(point_lng)
                distance = distance_km(point_lat, point_lng) if lat is not None and lng is not None else None
                places.append({
                    'name': (place.get('displayName') or {}).get('text') or 'Vehicle rental shop',
                    'type': 'Vehicle rental', 'address': place.get('formattedAddress', ''),
                    'lat': point_lat, 'lng': point_lng,
                    'distance_km': round(distance, 1) if distance is not None else None,
                    'rating': place.get('rating'), 'phone': place.get('nationalPhoneNumber'),
                    'maps_url': place.get('googleMapsUri'),
                })
            places.sort(key=lambda item: item.get('distance_km') if item.get('distance_km') is not None else 0)
            if places:
                return jsonify({'success': True, 'source': 'google-places', 'items': places[:8]})
        except (requests.RequestException, ValueError, TypeError) as error:
            app.logger.warning('Google Places search failed; using open-map fallback: %s', error)

    if lat is not None and lng is not None:
        query = (
            f'[out:json][timeout:6];(node(around:20000,{lat},{lng})[amenity~"car_rental|motorcycle_rental"];'
            f'way(around:20000,{lat},{lng})[amenity~"car_rental|motorcycle_rental"];'
            f'relation(around:20000,{lat},{lng})[amenity~"car_rental|motorcycle_rental"];);out center tags;'
        )
        endpoints = ('https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter')
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(requests.post, endpoint, data={'data': query}, timeout=(1.5, 3), headers={'User-Agent': 'QuickRent/1.0 nearby-shop-search'}) for endpoint in endpoints]
            try:
                completed = as_completed(pending, timeout=4.5)
                for future in completed:
                    try:
                        response = future.result()
                        response.raise_for_status()
                        elements = response.json().get('elements', [])
                        shops = []
                        for item in elements:
                            tags = item.get('tags') or {}
                            point_lat = item.get('lat', (item.get('center') or {}).get('lat'))
                            point_lng = item.get('lon', (item.get('center') or {}).get('lon'))
                            if not tags.get('name') or point_lat is None or point_lng is None:
                                continue
                            point_lat, point_lng = float(point_lat), float(point_lng)
                            address = ', '.join(filter(None, (tags.get('addr:housenumber'), tags.get('addr:street'), tags.get('addr:suburb') or tags.get('addr:city'))))
                            shops.append({'name': tags['name'], 'type': 'Vehicle rental', 'address': address, 'lat': point_lat, 'lng': point_lng, 'distance_km': round(distance_km(point_lat, point_lng), 1)})
                        shops.sort(key=lambda shop: shop['distance_km'])
                        if shops:
                            return jsonify({'success': True, 'source': 'openstreetmap', 'items': shops[:8]})
                    except (requests.RequestException, ValueError, TypeError):
                        continue
            except FuturesTimeoutError:
                pass

    # Photon indexes named real-world places from OpenStreetMap and biases
    # matches toward the requested coordinates. It fills gaps where a shop is
    # mapped but lacks the specific amenity tag Overpass searches above.
    try:
        photon_query = f'car rental near {area}' if area else 'car rental'
        params = {'q': photon_query, 'limit': 12}
        if lat is not None and lng is not None:
            params.update({'lat': lat, 'lon': lng})
        response = requests.get('https://photon.komoot.io/api/', params=params, timeout=(1.5, 3), headers={'User-Agent': 'QuickRent/1.0 nearby-shop-search'})
        response.raise_for_status()
        places = []
        for feature in response.json().get('features', []):
            props = feature.get('properties') or {}
            coordinates = (feature.get('geometry') or {}).get('coordinates') or []
            if not props.get('name') or len(coordinates) < 2:
                continue
            point_lng, point_lat = float(coordinates[0]), float(coordinates[1])
            distance = distance_km(point_lat, point_lng) if lat is not None and lng is not None else None
            if distance is not None and distance > 30:
                continue
            address = ', '.join(filter(None, (props.get('housenumber'), props.get('street'), props.get('district') or props.get('city'))))
            places.append({'name': props['name'], 'type': 'Rental search result', 'address': address, 'lat': point_lat, 'lng': point_lng, 'distance_km': round(distance, 1) if distance is not None else None})
        places.sort(key=lambda place: place.get('distance_km') if place.get('distance_km') is not None else 0)
        if places:
            return jsonify({'success': True, 'source': 'photon', 'items': places[:8]})
    except (requests.RequestException, ValueError, TypeError):
        pass

    try:
        vehicles = db.table('vehicles').select('id, name, type, daily_rate, latitude, longitude').eq('status', 'available').execute().data or []
    except Exception:
        # Location columns may not exist in older Supabase deployments until
        # their schema migration is applied. Still return available inventory.
        try:
            vehicles = db.table('vehicles').select('id, name, type, daily_rate').eq('status', 'available').execute().data or []
        except Exception:
            vehicles = []
    nearby = []
    inventory = []
    for vehicle in vehicles:
        item = {'id': vehicle.get('id'), 'name': vehicle.get('name') or 'Available vehicle', 'type': vehicle.get('type') or 'vehicle', 'daily_rate': vehicle.get('daily_rate')}
        inventory.append(item)
        try:
            point_lat, point_lng = float(vehicle['latitude']), float(vehicle['longitude'])
            if -90 <= point_lat <= 90 and -180 <= point_lng <= 180:
                item.update({'lat': point_lat, 'lng': point_lng, 'distance_km': round(distance_km(point_lat, point_lng), 1)})
                nearby.append(item)
        except (KeyError, TypeError, ValueError):
            continue
    nearby.sort(key=lambda vehicle: vehicle['distance_km'])
    if nearby:
        return jsonify({'success': True, 'source': 'quickrent-nearby', 'items': nearby[:8]})
    if inventory:
        return jsonify({'success': True, 'source': 'quickrent-inventory', 'items': inventory[:8]})
    map_search = f'car rental shops near {area}' if area else f'car rental shops near {lat},{lng}'
    return jsonify({'success': True, 'source': 'open-map-search', 'items': [{'name': f'Car rental shops near {area}' if area else 'Car rental shops near your location', 'type': 'OpenStreetMap search', 'address': 'Open the map search to see vehicle rental businesses in this area.', 'search_query': map_search, 'lat': lat, 'lng': lng}]})

@app.route('/customer/vehicles')
@customer_login_required
def customer_vehicles():
    try:
        type_filter = request.args.get('type', 'all')
        status_filter = request.args.get('status', 'all')
        tier_filter = request.args.get('tier', 'all')
        body_style_filter = request.args.get('body_style', 'all')
        query = db.table('vehicles').select('*').order('name')
        if type_filter != 'all': query = query.eq('type', type_filter)
        if status_filter == 'available': query = query.eq('status', 'available')
        if tier_filter in ('regular', 'premium'):
            query = query.eq('type', 'car').eq('tier', tier_filter)
        if body_style_filter in ('suv', 'sedan', 'hatchback', 'motorcycle', 'scooter'): query = query.eq('body_style', body_style_filter)
        vehicles_res = query.execute()
        return render_template('customer/vehicles.html', vehicles=vehicles_res.data or [], type_filter=type_filter, status_filter=status_filter, tier_filter=tier_filter, body_style_filter=body_style_filter, current_page='vehicles')
    except Exception:
        return render_template('customer/vehicles.html', vehicles=[], type_filter='all', status_filter='all', tier_filter='all', body_style_filter='all', current_page='vehicles')

@app.route('/customer/bookings')
@customer_login_required
def customer_bookings():
    try:
        customer_id = session['customer']['id']
        status = request.args.get('status', 'all')
        query = db.table('bookings').select('*, vehicles(name, type, daily_rate, fuel, year)').eq('customer_id', customer_id).order('created_at', desc=True)
        if status != 'all': query = query.eq('status', status)
        bookings = query.execute()
        return render_template('customer/bookings.html', bookings=bookings.data or [], active_filter=status, current_page='bookings')
    except Exception:
        return render_template('customer/bookings.html', bookings=[], active_filter='all', current_page='bookings')

@app.route('/customer/booking/<booking_id>')
@customer_login_required
def customer_booking_detail(booking_id):
    cid = session['customer']['id']
    booking = db.table('bookings').select('*, vehicles(name,type,daily_rate,fuel,year,brand)').eq('id', booking_id).eq('customer_id', cid).execute()
    if not booking.data: return redirect(url_for('customer_bookings'))
    b = booking.data[0]
    payments = db.table('payments').select('*').eq('booking_id', booking_id).execute()
    
    try:
        days = (datetime.strptime(b['end_date'], '%Y-%m-%d') - datetime.strptime(b['start_date'], '%Y-%m-%d')).days
        if days == 0: days = 1
    except: days = 1
        
    vehicle = b.get('vehicles') or {}
    daily = vehicle.get('daily_rate', 0)
    base = daily * days
    tax = round(base * 0.18, 2)
    return render_template('customer/booking_detail.html', booking=b, payments=payments.data or [], days=days, base_rate=base, tax=tax, total=base+tax, current_page='bookings')

@app.route('/customer/profile', methods=['GET', 'POST'])
@customer_login_required
def customer_profile():
    cid = session['customer']['id']
    if request.method == 'POST':
        data = request.form
        db.table('customers').update({
            'name': data.get('name'), 'phone': data.get('phone'), 'city': data.get('city'),
            'license_number': data.get('license_number'), 'license_expiry': data.get('license_expiry') or None,
            'preferred_payment': data.get('preferred_payment'), 'profile_complete': True
        }).eq('id', cid).execute()
        if data.get('name'):
            session['customer']['name'] = data.get('name')
            session.modified = True
        return redirect(url_for('customer_profile') + '?saved=1')
        
    customer = db.table('customers').select('*').eq('id', cid).execute()
    bookings = db.table('bookings').select('*').eq('customer_id', cid).execute()
    total_spent = sum(b['total_amount'] for b in (bookings.data or []) if b['status'] == 'completed')
    
    return render_template('customer/profile.html', customer=customer.data[0] if customer.data else session['customer'], total_bookings=len(bookings.data or []), total_spent=total_spent, saved=request.args.get('saved'), current_page='profile')

@app.route('/customer/wishlist')
@customer_login_required
def customer_wishlist():
    cid = session['customer']['id']
    wishlist = db.table('wishlists').select('*, vehicles(id,name,type,daily_rate,fuel,year,status)').eq('customer_id', cid).execute()
    all_vehicles = db.table('vehicles').select('*').eq('status', 'available').execute()
    wishlisted_ids = [w['vehicle_id'] for w in (wishlist.data or [])]
    return render_template('customer/wishlist.html', wishlist=wishlist.data or [], all_vehicles=all_vehicles.data or [], wishlisted_ids=wishlisted_ids, current_page='vehicles')

@app.route('/customer/reviews')
@customer_login_required
def customer_reviews():
    cid = session['customer']['id']
    completed = db.table('bookings').select('*, vehicles(id,name,type)').eq('customer_id', cid).eq('status', 'completed').execute()
    existing = db.table('reviews').select('*').eq('customer_id', cid).execute()
    reviewed_booking_ids = [r['booking_id'] for r in (existing.data or [])]
    return render_template('customer/reviews.html', completed=completed.data or [], existing_reviews=existing.data or [], reviewed_booking_ids=reviewed_booking_ids, current_page='profile')

@app.route('/customer/invoices')
@customer_login_required
def customer_invoices():
    cid = session['customer']['id']
    bookings = db.table('bookings').select('*, vehicles(name,type)').eq('customer_id', cid).in_('status', ['active', 'completed']).order('created_at', desc=True).execute()
    return render_template('customer/invoices.html', bookings=bookings.data or [], current_page='bookings')

@app.route('/customer/invoice/<booking_id>/pdf')
@customer_login_required
def download_invoice(booking_id):
    cid = session['customer']['id']
    booking = db.table('bookings').select('*, vehicles(name,type,daily_rate), customers(name,email,phone)').eq('id', booking_id).eq('customer_id', cid).execute()
    if not booking.data: return redirect(url_for('customer_invoices'))
    b = booking.data[0]
    
    try:
        days = (datetime.strptime(b['end_date'], '%Y-%m-%d') - datetime.strptime(b['start_date'], '%Y-%m-%d')).days
        if days == 0: days = 1
    except: days = 1
        
    invoice_vehicle = b.get('vehicles') or {}
    invoice_customer = b.get('customers') or {}
    daily = invoice_vehicle.get('daily_rate', 0)
    base = daily * days
    tax = round(base * 0.18, 2)
    total = round(base + tax, 2)
    safe = lambda value: str(value).encode('ascii', 'replace').decode('ascii').replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    rows = [
        'RENTAL INVOICE',
        f'Invoice date: {datetime.now().strftime("%d %b %Y")}',
        f'Booking reference: {b.get("booking_ref", "-")}',
        f'Customer: {invoice_customer.get("name", session["customer"].get("name", "Customer"))}',
        f'Email: {invoice_customer.get("email", session["customer"].get("email", "-"))}',
        f'Vehicle: {invoice_vehicle.get("name", "Vehicle rental")}',
        f'Pickup: {b.get("start_date", "-")}',
        f'Return: {b.get("end_date", "-")}',
        f'Rental duration: {days} day(s)',
        f'Daily rate: INR {daily:,.2f}',
        f'Base amount: INR {base:,.2f}',
        f'Tax (18%): INR {tax:,.2f}',
        f'Total: INR {total:,.2f}',
        f'Payment status: {b.get("payment_status", "pending")}',
        'Thank you for choosing QuickRent.',
    ]
    content_lines = ['BT', '/F2 20 Tf', '50 740 Td', '(QuickRent) Tj', '/F1 12 Tf', '0 -32 Td']
    for index, row in enumerate(rows):
        if index:
            content_lines.append('0 -25 Td')
        if row == 'RENTAL INVOICE':
            content_lines.append('/F2 14 Tf')
        elif index > 0:
            content_lines.append('/F1 11 Tf')
        content_lines.append(f'({safe(row)}) Tj')
    content_lines.append('ET')
    content = ('\n'.join(content_lines) + '\n').encode('ascii')
    pdf_objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>',
        b'<< /Length ' + str(len(content)).encode('ascii') + b' >>\nstream\n' + content + b'endstream',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, obj in enumerate(pdf_objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f'{index} 0 obj\n'.encode('ascii') + obj + b'\nendobj\n')
    xref_offset = len(pdf)
    pdf.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode('ascii'))
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    pdf.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n'.encode('ascii'))
    filename = secure_filename(f'invoice-{b.get("booking_ref", "QuickRent")}.pdf')
    return app.response_class(bytes(pdf), mimetype='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})

# ══════════════════════════════════════
# CUSTOMER API ROUTES (Booking, Canceling, etc.)
# ══════════════════════════════════════
@app.route('/api/customer/bookings/create', methods=['POST'])
@customer_login_required
def customer_create_booking():
    try:
        data = request.get_json(silent=True) or {}
        customer_id = session['customer']['id']
        try:
            start_date = datetime.strptime(data.get('start_date', ''), '%Y-%m-%d').date()
            end_date = datetime.strptime(data.get('end_date', ''), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Choose valid rental dates.'}), 400
        if start_date < datetime.now().date() or end_date <= start_date:
            return jsonify({'success': False, 'error': 'Choose a future pickup date and a later return date.'}), 400
        if not data.get('vehicle_id'):
            return jsonify({'success': False, 'error': 'Choose a vehicle to continue.'}), 400

        vehicle = db.table('vehicles').select('status, daily_rate, name').eq('id', data['vehicle_id']).execute()
        
        if not vehicle.data: return jsonify({'success': False, 'error': 'Vehicle not found'}), 404
        if vehicle.data[0]['status'] != 'available': return jsonify({'success': False, 'error': 'Vehicle is no longer available'}), 400

        route_fields = ('pickup_location', 'dropoff_location', 'pickup_latitude', 'pickup_longitude', 'dropoff_latitude', 'dropoff_longitude', 'distance_km')
        if any(data.get(field) is not None for field in route_fields):
            try:
                if not str(data.get('pickup_location') or '').strip() or not str(data.get('dropoff_location') or '').strip():
                    raise ValueError('Missing pickup or drop-off label')
                pickup_lat = float(data['pickup_latitude'])
                pickup_lng = float(data['pickup_longitude'])
                dropoff_lat = float(data['dropoff_latitude'])
                dropoff_lng = float(data['dropoff_longitude'])
                distance_km = float(data['distance_km'])
                duration_value = data.get('estimated_duration_minutes')
                duration_minutes = int(duration_value) if duration_value is not None else None
                if not (-90 <= pickup_lat <= 90 and -180 <= pickup_lng <= 180 and
                        -90 <= dropoff_lat <= 90 and -180 <= dropoff_lng <= 180 and 0 <= distance_km <= 50000):
                    raise ValueError('Out-of-range coordinates or distance')
                if duration_minutes is not None and not 0 <= duration_minutes <= 100000:
                    raise ValueError('Out-of-range route duration')
            except (KeyError, TypeError, ValueError):
                return jsonify({'success': False, 'error': 'Choose valid pickup and drop-off points.'}), 400
        else:
            pickup_lat = pickup_lng = dropoff_lat = dropoff_lng = distance_km = None
            duration_minutes = None

        ref = 'BK-' + ''.join(random.choices(string.digits, k=4))
        rental_days = (end_date - start_date).days
        total_amount = round(rental_days * float(vehicle.data[0]['daily_rate']), 2)
        db.table('bookings').insert({
            'booking_ref': ref, 'customer_id': customer_id, 'vehicle_id': data['vehicle_id'],
            'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(), 'total_amount': total_amount,
            'pickup_location': data.get('pickup_location'), 'dropoff_location': data.get('dropoff_location'),
            'pickup_latitude': pickup_lat, 'pickup_longitude': pickup_lng,
            'dropoff_latitude': dropoff_lat, 'dropoff_longitude': dropoff_lng,
            'distance_km': distance_km,
            'estimated_duration_minutes': duration_minutes,
            'status': 'pending', 'payment_status': 'pending'
        }).execute()
        db.table('vehicles').update({'status': 'rented'}).eq('id', data['vehicle_id']).execute()
        return jsonify({'success': True, 'booking_ref': ref, 'total_amount': total_amount})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customer/bookings/<booking_id>/cancel', methods=['POST'])
@customer_login_required
def customer_cancel_booking(booking_id):
    try:
        cid = session['customer']['id']
        booking = db.table('bookings').select('customer_id, vehicle_id, status, start_date, booking_ref').eq('id', booking_id).execute()
        
        if not booking.data: return jsonify({'success': False, 'error': 'Booking not found'}), 404
        b = booking.data[0]
        if b['customer_id'] != cid: return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        if b['status'] in ['completed', 'cancelled']: return jsonify({'success': False, 'error': 'Cannot cancel this booking'}), 400

        db.table('bookings').update({'status': 'cancelled'}).eq('id', booking_id).execute()
        if b.get('vehicle_id'): db.table('vehicles').update({'status': 'available'}).eq('id', b['vehicle_id']).execute()
        
        customer = db.table('customers').select('email,name').eq('id', cid).execute()
        if customer.data:
            send_email(customer.data[0]['email'], 'Booking Cancelled — QuickRent',
                f"<p>Hi {customer.data[0]['name']},</p><p>Your booking <strong>{b['booking_ref']}</strong> has been cancelled.</p><p>If you paid, refund will be processed in 5–7 business days.</p><p>— QuickRent Team</p>")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customer/bookings/<booking_id>/extend', methods=['POST'])
@customer_login_required
def extend_booking(booking_id):
    cid = session['customer']['id']
    data = request.json
    new_end = data.get('new_end_date')
    booking = db.table('bookings').select('*, vehicles(daily_rate)').eq('id', booking_id).eq('customer_id', cid).execute()
    if not booking.data: return jsonify({'success': False, 'error': 'Not found'})
    b = booking.data[0]
    
    try:
        old_days = (datetime.strptime(b['end_date'], '%Y-%m-%d') - datetime.strptime(b['start_date'], '%Y-%m-%d')).days
        new_days = (datetime.strptime(new_end, '%Y-%m-%d') - datetime.strptime(b['start_date'], '%Y-%m-%d')).days
        if new_days <= old_days: return jsonify({'success': False, 'error': 'New date must be after current end date'})
        
        daily = b['vehicles']['daily_rate']
        extra_amount = (new_days - old_days) * daily * 1.18
        new_total = round(b['total_amount'] + extra_amount, 2)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
        
    db.table('bookings').update({'end_date': new_end, 'total_amount': new_total}).eq('id', booking_id).execute()
    return jsonify({'success': True, 'new_total': new_total})

@app.route('/api/customer/wishlist/toggle', methods=['POST'])
@customer_login_required
def toggle_wishlist():
    cid = session['customer']['id']
    vehicle_id = request.json.get('vehicle_id')
    existing = db.table('wishlists').select('id').eq('customer_id', cid).eq('vehicle_id', vehicle_id).execute()
    if existing.data:
        db.table('wishlists').delete().eq('id', existing.data[0]['id']).execute()
        return jsonify({'success': True, 'action': 'removed'})
    db.table('wishlists').insert({'customer_id': cid, 'vehicle_id': vehicle_id}).execute()
    return jsonify({'success': True, 'action': 'added'})

@app.route('/api/customer/review/submit', methods=['POST'])
@customer_login_required
def submit_review():
    cid = session['customer']['id']
    data = request.json
    existing = db.table('reviews').select('id').eq('booking_id', data['booking_id']).eq('customer_id', cid).execute()
    if existing.data: return jsonify({'success': False, 'error': 'Already reviewed'})
    db.table('reviews').insert({'customer_id': cid, 'vehicle_id': data['vehicle_id'], 'booking_id': data['booking_id'], 'rating': int(data['rating']), 'comment': data.get('comment', '')}).execute()
    return jsonify({'success': True})

@app.route('/api/customer/profile/update', methods=['POST'])
@customer_login_required
def customer_update_profile_api():
    try:
        cid = session['customer']['id']
        data = request.json
        db.table('customers').update({'name': data['name'], 'phone': data.get('phone', ''), 'city': data.get('city', '')}).eq('id', cid).execute()
        session['customer']['name'] = data['name']
        session.modified = True
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# RAZORPAY
@app.route('/api/customer/payment/create', methods=['POST'])
@customer_login_required
def create_razorpay_order():
    try:
        import razorpay
        data = request.json
        amount = data['amount']
        rz_key_id = os.environ.get('RAZORPAY_KEY_ID')
        client = razorpay.Client(auth=(rz_key_id, os.environ.get('RAZORPAY_KEY_SECRET')))
        order = client.order.create({'amount': amount * 100, 'currency': 'INR', 'receipt': data['booking_id'][:20], 'payment_capture': 1})
        return jsonify({'success': True, 'order_id': order['id'], 'key_id': rz_key_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customer/payment/verify', methods=['POST'])
@customer_login_required
def verify_razorpay_payment():
    try:
        import hmac, hashlib
        data = request.json
        rz_key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
        body = data['razorpay_order_id'] + '|' + data['razorpay_payment_id']
        expected = hmac.new(rz_key_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        
        if expected != data['razorpay_signature']: return jsonify({'success': False, 'error': 'Invalid signature'}), 400

        ref = '#TXN-' + ''.join(random.choices(string.digits, k=6))
        db.table('payments').insert({'transaction_ref': ref, 'booking_id': data['booking_id'], 'customer_id': session['customer']['id'], 'amount': data['amount'], 'method': 'Razorpay', 'status': 'paid'}).execute()
        db.table('bookings').update({'payment_status': 'paid', 'payment_method': 'Razorpay'}).eq('id', data['booking_id']).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ══════════════════════════════════════
# ERROR HANDLERS
# ══════════════════════════════════════
@app.errorhandler(404)
def not_found(e): return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e): return render_template('505.html'), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
