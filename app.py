# app.py
# This is your main Flask application file.
# It defines every URL route your website responds to.

from flask import Flask, render_template, jsonify, request, redirect, url_for
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, FLASK_SECRET_KEY
from datetime import date

# ── CREATE FLASK APP ──
# Flask(__name__) creates your app.
# __name__ tells Flask where to find templates/ and static/ folders.
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# ── CONNECT TO SUPABASE ──
# create_client() returns a Supabase client object.
# We call it 'db' — use db.table('...').select()... to query.
db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ══════════════════════════════════════
# SIDEBAR COMPONENT ROUTE
# ══════════════════════════════════════
# This serves the sidebar HTML to any page that fetches it.
# Your sidebar.js calls fetch('/components/sidebar')
# Flask intercepts that URL and returns the sidebar HTML fragment.
@app.route('/components/sidebar')
def sidebar_component():
    return render_template('components/sidebar.html')


# ══════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════
@app.route('/')
@app.route('/dashboard')
def dashboard():
    # Fetch summary counts from Supabase
    # .select('*', count='exact') returns both data AND a count
    # We use count to show totals on the dashboard cards

    vehicles_res = db.table('vehicles').select('*', count='exact').execute()
    bookings_res = db.table('bookings').select('*', count='exact').execute()
    customers_res = db.table('customers').select('*', count='exact').execute()

    # Count vehicles by status
    available = db.table('vehicles').select('*', count='exact').eq('status', 'available').execute()
    rented = db.table('vehicles').select('*', count='exact').eq('status', 'rented').execute()
    maintenance = db.table('vehicles').select('*', count='exact').eq('status', 'maintenance').execute()

    # Count bookings by status
    active_bookings = db.table('bookings').select('*', count='exact').eq('status', 'active').execute()
    pending_bookings = db.table('bookings').select('*', count='exact').eq('status', 'pending').execute()
    overdue_bookings = db.table('bookings').select('*', count='exact').eq('status', 'overdue').execute()

    # Fetch 5 most recent bookings with customer and vehicle info
    # This is a JOIN — it fetches related data from other tables in one query
    recent_bookings = db.table('bookings')\
        .select('*, customers(name), vehicles(name, type)')\
        .order('created_at', desc=True)\
        .limit(5)\
        .execute()

    # Calculate total revenue from paid payments
    payments_res = db.table('payments').select('amount').eq('status', 'paid').execute()
    total_revenue = sum(p['amount'] for p in payments_res.data) if payments_res.data else 0

    # render_template fills your HTML file with Python variables.
    # The variable names on the left become available in HTML as {{ variable_name }}
    return render_template('dashboard.html',
        total_vehicles=vehicles_res.count or 0,
        total_bookings=bookings_res.count or 0,
        total_customers=customers_res.count or 0,
        total_revenue=total_revenue,
        available_vehicles=available.count or 0,
        rented_vehicles=rented.count or 0,
        maintenance_vehicles=maintenance.count or 0,
        active_bookings=active_bookings.count or 0,
        pending_bookings=pending_bookings.count or 0,
        overdue_bookings=overdue_bookings.count or 0,
        recent_bookings=recent_bookings.data or []
    )


# ══════════════════════════════════════
# BOOKINGS
# ══════════════════════════════════════
@app.route('/bookings')
def bookings():
    # Get optional filter from URL query string
    # e.g. /bookings?status=active
    # request.args.get() reads query parameters safely
    status_filter = request.args.get('status', 'all')

    query = db.table('bookings')\
        .select('*, customers(name, phone), vehicles(name, type)')\
        .order('created_at', desc=True)

    # Apply filter if not 'all'
    if status_filter != 'all':
        query = query.eq('status', status_filter)

    bookings_res = query.execute()

    # Count by status for the summary strip
    counts = {
        'all': db.table('bookings').select('*', count='exact').execute().count or 0,
        'active': db.table('bookings').select('*', count='exact').eq('status', 'active').execute().count or 0,
        'pending': db.table('bookings').select('*', count='exact').eq('status', 'pending').execute().count or 0,
        'overdue': db.table('bookings').select('*', count='exact').eq('status', 'overdue').execute().count or 0,
        'completed': db.table('bookings').select('*', count='exact').eq('status', 'completed').execute().count or 0,
    }

    return render_template('bookings.html',
        bookings=bookings_res.data or [],
        counts=counts,
        active_filter=status_filter
    )


# ══════════════════════════════════════
# VEHICLES
# ══════════════════════════════════════
@app.route('/vehicles')
def vehicles():
    type_filter = request.args.get('type', 'all')

    query = db.table('vehicles').select('*').order('created_at', desc=True)

    if type_filter == 'car':
        query = query.eq('type', 'car')
    elif type_filter == 'bike':
        query = query.eq('type', 'bike')
    elif type_filter == 'unavailable':
        query = query.neq('status', 'available')

    vehicles_res = query.execute()

    return render_template('vehicles.html',
        vehicles=vehicles_res.data or [],
        active_filter=type_filter
    )


# ══════════════════════════════════════
# CUSTOMERS
# ══════════════════════════════════════
@app.route('/customers')
def customers():
    customers_res = db.table('customers')\
        .select('*')\
        .order('created_at', desc=True)\
        .execute()

    counts = {
        'total': db.table('customers').select('*', count='exact').execute().count or 0,
    }

    return render_template('customers.html',
        customers=customers_res.data or [],
        counts=counts
    )


# ══════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════
@app.route('/payments')
def payments():
    status_filter = request.args.get('status', 'all')

    query = db.table('payments')\
        .select('*, bookings(booking_ref), customers(name)')\
        .order('created_at', desc=True)

    if status_filter != 'all':
        query = query.eq('status', status_filter)

    payments_res = query.execute()

    # Revenue stats
    all_payments = db.table('payments').select('amount, status').execute()
    total_collected = sum(p['amount'] for p in all_payments.data if p['status'] == 'paid') if all_payments.data else 0
    total_pending = sum(p['amount'] for p in all_payments.data if p['status'] == 'pending') if all_payments.data else 0

    return render_template('payments.html',
        payments=payments_res.data or [],
        active_filter=status_filter,
        total_collected=total_collected,
        total_pending=total_pending
    )


# ══════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════
@app.route('/analytics')
def analytics():
    vehicles_res = db.table('vehicles').select('*').execute()
    bookings_res = db.table('bookings').select('*').execute()
    customers_res = db.table('customers').select('*').execute()
    payments_res = db.table('payments').select('amount, status').execute()

    total_revenue = sum(p['amount'] for p in payments_res.data if p['status'] == 'paid') if payments_res.data else 0

    # Count bookings by vehicle type using Python
    type_counts = {'car': 0, 'bike': 0, 'scooter': 0}
    for b in bookings_res.data or []:
        pass  # will be enriched with joins in a later phase

    return render_template('analytics.html',
        total_revenue=total_revenue,
        total_bookings=len(bookings_res.data or []),
        total_vehicles=len(vehicles_res.data or []),
        total_customers=len(customers_res.data or [])
    )


# ══════════════════════════════════════
# RENTALS
# ══════════════════════════════════════
@app.route('/rentals')
def rentals():
    active = db.table('bookings')\
        .select('*, vehicles(name, type), customers(name)')\
        .in_('status', ['active', 'pending'])\
        .order('created_at', desc=True)\
        .execute()

    past = db.table('bookings')\
        .select('*, vehicles(name, type), customers(name)')\
        .in_('status', ['completed', 'overdue'])\
        .order('created_at', desc=True)\
        .execute()

    return render_template('rentals.html',
        active_rentals=active.data or [],
        past_rentals=past.data or []
    )


# ══════════════════════════════════════
# SETTINGS / NOTIFICATIONS / HELP
# ══════════════════════════════════════
@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/notifications')
def notifications():
    return render_template('notifications.html')

@app.route('/help')
def help_page():
    return render_template('help.html')


# ══════════════════════════════════════
# API ROUTES — for adding data
# ══════════════════════════════════════
# These routes receive form data and insert into Supabase.
# They use POST method — for sending data (not just reading it).

@app.route('/api/vehicles/add', methods=['POST'])
def add_vehicle():
    # request.json reads JSON data sent from the browser
    data = request.json
    result = db.table('vehicles').insert({
        'name': data['name'],
        'type': data['type'],
        'brand': data.get('brand', ''),
        'year': data.get('year'),
        'fuel': data.get('fuel', 'Petrol'),
        'daily_rate': data['daily_rate'],
        'status': 'available'
    }).execute()
    # jsonify sends a JSON response back to the browser
    return jsonify({'success': True, 'vehicle': result.data})


@app.route('/api/customers/add', methods=['POST'])
def add_customer():
    data = request.json
    result = db.table('customers').insert({
        'name': data['name'],
        'email': data['email'],
        'phone': data.get('phone', ''),
        'city': data.get('city', '')
    }).execute()
    return jsonify({'success': True, 'customer': result.data})


@app.route('/api/bookings/add', methods=['POST'])
def add_booking():
    data = request.json
    import random, string
    # Generate a booking reference like BK-2450
    ref = 'BK-' + ''.join(random.choices(string.digits, k=4))
    result = db.table('bookings').insert({
        'booking_ref': ref,
        'customer_id': data['customer_id'],
        'vehicle_id': data['vehicle_id'],
        'start_date': data['start_date'],
        'end_date': data['end_date'],
        'total_amount': data['total_amount'],
        'status': 'pending',
        'payment_status': 'pending'
    }).execute()
    # Update vehicle status to rented
    db.table('vehicles').update({'status': 'rented'}).eq('id', data['vehicle_id']).execute()
    return jsonify({'success': True, 'booking': result.data})


@app.route('/api/bookings/status', methods=['POST'])
def update_booking_status():
    data = request.json
    db.table('bookings').update({'status': data['status']}).eq('id', data['booking_id']).execute()
    # If completed, free up the vehicle
    if data['status'] == 'completed':
        booking = db.table('bookings').select('vehicle_id').eq('id', data['booking_id']).execute()
        if booking.data:
            db.table('vehicles').update({'status': 'available'}).eq('id', booking.data[0]['vehicle_id']).execute()
    return jsonify({'success': True})


# ══════════════════════════════════════
# RUN THE APP
# ══════════════════════════════════════
# debug=True means:
# 1. Flask auto-reloads when you save a file
# 2. Shows detailed error pages in the browser
# NEVER use debug=True in production (when your site is live)
if __name__ == '__main__':
    app.run(debug=True, port=5001)