from flask import Flask, g, render_template, request, jsonify, redirect, url_for, session
import json
import math
import os
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / 'frontend'

app = Flask(
    __name__,
    template_folder=str(FRONTEND_DIR / 'templates'),
    static_folder=str(FRONTEND_DIR / 'static'),
)
app.config['JSON_AS_ASCII'] = False
app.config['AUTH_SESSION_ID'] = secrets.token_urlsafe(32)
app.secret_key = 'f3utur3-pr3mium-h0st'

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'Admin1234!'
EMPLOYEE_USERNAME = 'empleado'
EMPLOYEE_PASSWORD = 'Empleado1234!'

EMPLOYEE_PERMISSIONS = {
    'clients': {'GET'},
    'api_clients': {'GET', 'POST'},
    'api_client_detail': {'GET'},
    'inventory': {'GET'},
    'api_inventory': {'GET'},
    'api_inventory_detail': {'GET'},
    'sales': {'GET'},
    'api_sales': {'GET', 'POST'},
    'api_sales_by_date': {'POST'},
    'api_sale_detail': {'GET'},
    'invoices': {'GET'},
    'api_invoices': {'GET'},
    'api_invoice_detail': {'GET'},
    'purchases': {'GET'},
    'api_purchases': {'GET', 'POST'},
    'api_purchase_detail': {'GET'},
    'expenses': {'GET'},
    'api_expenses': {'GET', 'POST'},
    'api_expense_detail': {'GET'},
    'logout': {'GET'},
}

HISTORY_EVENTS = {
    ('api_inventory', 'POST'): ('Inventario', 'Producto agregado'),
    ('api_inventory_detail', 'PUT'): ('Inventario', 'Producto actualizado'),
    ('api_inventory_detail', 'DELETE'): ('Inventario', 'Producto eliminado'),
    ('api_sales', 'POST'): ('Ventas', 'Venta registrada'),
    ('api_sale_detail', 'DELETE'): ('Ventas', 'Venta eliminada'),
    ('api_purchases', 'POST'): ('Compras', 'Compra registrada'),
    ('api_purchase_detail', 'DELETE'): ('Compras', 'Compra eliminada'),
    ('api_expenses', 'POST'): ('Gastos', 'Gasto registrado'),
    ('api_expense_detail', 'DELETE'): ('Gastos', 'Gasto eliminado'),
}

# Rutas de archivos del backend
FILES_DIR = BASE_DIR / 'files'
FILES_DIR.mkdir(exist_ok=True)

CLIENTS_FILE = FILES_DIR / "client.txt"
SUPPLIERS_FILE = FILES_DIR / "supplier.txt"
SALES_FILE = FILES_DIR / "sale.txt"
BUYS_FILE = FILES_DIR / "buys.txt"
STOCK_FILE = FILES_DIR / "stocktaking.txt"
INVOICES_FILE = FILES_DIR / "invoices.txt"
EXPENSES_FILE = FILES_DIR / "expenses.txt"
HISTORY_FILE = FILES_DIR / "history.txt"

# Funciones auxiliares
def ensure_file_exists(filepath):
    """Asegura que el archivo exista"""
    path = Path(filepath)
    if not path.exists():
        path.touch(exist_ok=True)

def read_json_file(filepath):
    """Lee un archivo de líneas JSON"""
    ensure_file_exists(filepath)
    data = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return []
    return data

def write_json_file(filepath, data):
    """Escribe una línea JSON en el archivo"""
    ensure_file_exists(filepath)
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')

def get_next_id(filepath):
    """Obtiene el siguiente ID disponible"""
    data = read_json_file(filepath)
    if not data:
        return 1
    return max(item.get('id', 0) for item in data) + 1

def find_entity_by_id(filepath, entity_id):
    """Encuentra una entidad por ID"""
    data = read_json_file(filepath)
    for item in data:
        if item.get('id') == entity_id:
            return item
    return None

def find_entity_by_name(filepath, name):
    """Encuentra una entidad por nombre"""
    data = read_json_file(filepath)
    for item in data:
        full_name = f"{item.get('name', '')} {item.get('last_name', '')}".strip()
        if full_name.lower() == name.lower() or item.get('name', '').lower() == name.lower():
            return item
    return None

def is_logged_in():
    tab_token = (
        request.headers.get('X-Tab-Token')
        or request.args.get('tab_token')
        or request.form.get('tab_token')
    )
    stored_tab_token = session.get('auth_tab_token')
    return (
        session.get('logged_in', False)
        and session.get('auth_session_id') == app.config['AUTH_SESSION_ID']
        and isinstance(tab_token, str)
        and isinstance(stored_tab_token, str)
        and secrets.compare_digest(tab_token, stored_tab_token)
    )

@app.context_processor
def inject_auth_context():
    return {'is_logged_in': is_logged_in}

@app.before_request
def require_login():
    authenticated = is_logged_in()
    g.audit_user = session.get('admin_user', 'Anónimo') if authenticated else 'Anónimo'
    g.audit_role = session.get('role', 'public') if authenticated else 'public'

    if request.endpoint in ('index', 'login', 'static') or request.path.startswith('/static/'):
        return
    if not is_logged_in():
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Inicia sesión para continuar'}), 401
        return redirect(url_for('login', next=request.path))
    if session.get('role') == 'admin':
        return
    allowed_methods = EMPLOYEE_PERMISSIONS.get(request.endpoint, set())
    if session.get('role') != 'employee' or request.method not in allowed_methods:
        if request.path.startswith('/api/'):
            return jsonify({'error': 'No tienes permiso para realizar esta acción'}), 403
        return render_template('forbidden.html'), 403

@app.after_request
def log_activity(response):
    response.headers['Referrer-Policy'] = 'no-referrer'
    if is_logged_in():
        response.headers['Cache-Control'] = 'no-store'

    event = HISTORY_EVENTS.get((request.endpoint, request.method))
    if event is None or response.status_code >= 400:
        return response

    entity, action = event
    response_data = response.get_json(silent=True)
    if isinstance(response_data, dict) and 'data' in response_data:
        details = response_data['data']
        if request.endpoint == 'api_sales':
            details = {'sale': details, 'invoice': response_data.get('invoice')}
    else:
        details = request.view_args or request.get_json(silent=True) or {}

    entry = {
        'date_time': datetime.now().astimezone().isoformat(timespec='seconds'),
        'user': session.get('admin_user', 'Anónimo'),
        'role': session.get('role', 'public'),
        'entity': entity,
        'action': action,
        'method': request.method,
        'path': request.path,
        'status': response.status_code,
        'details': details,
    }
    write_json_file(HISTORY_FILE, entry)
    return response

def get_history_event(entry):
    entity = entry.get('entity')
    action = entry.get('action')
    if entity in {'Inventario', 'Ventas', 'Compras', 'Gastos'} and action:
        return entity, action

    method = entry.get('method')
    path = entry.get('path', '')
    legacy_events = {
        ('/api/inventory', 'POST'): ('Inventario', 'Producto agregado'),
        ('/api/sales', 'POST'): ('Ventas', 'Venta registrada'),
        ('/api/purchases', 'POST'): ('Compras', 'Compra registrada'),
        ('/api/expenses', 'POST'): ('Gastos', 'Gasto registrado'),
    }
    if (path, method) in legacy_events:
        return legacy_events[(path, method)]

    detail_events = {
        '/api/inventory/': {'PUT': ('Inventario', 'Producto actualizado'), 'DELETE': ('Inventario', 'Producto eliminado')},
        '/api/sales/': {'DELETE': ('Ventas', 'Venta eliminada')},
        '/api/purchases/': {'DELETE': ('Compras', 'Compra eliminada')},
        '/api/expenses/': {'DELETE': ('Gastos', 'Gasto eliminado')},
    }
    for prefix, methods in detail_events.items():
        item_id = path.removeprefix(prefix)
        if path.startswith(prefix) and item_id.isdecimal() and method in methods:
            return methods[method]
    return None

def format_history_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(amount):
        return str(value)

    whole, fraction = f'{abs(amount):,.2f}'.split('.')
    whole = whole.replace(',', '.')
    fraction = fraction.rstrip('0')
    formatted = whole + (',' + fraction if fraction else '')
    return f"{'-' if amount < 0 else ''}${formatted}"

def format_history_details(entry):
    details = entry.get('details') or {}
    if not isinstance(details, dict):
        return []

    entity = entry.get('entity')
    if entity == 'Ventas':
        sale = details.get('sale', details)
        invoice = details.get('invoice') or {}
        fields = [
            ('Factura', invoice.get('invoice_id')),
            ('Venta', sale.get('id')),
            ('Cliente', sale.get('client_name')),
            ('Producto', sale.get('product_name')),
            ('Cantidad', sale.get('quantity')),
            ('Precio unitario', sale.get('unit_price')),
            ('Total', sale.get('total')),
            ('Método de pago', sale.get('payment_method')),
            ('Fecha', sale.get('date')),
        ]
        amount_labels = {'Precio unitario', 'Total'}
    elif entity == 'Inventario':
        fields = [
            ('ID de producto', details.get('id')),
            ('Producto', details.get('name')),
            ('Precio de venta', details.get('price')),
            ('Existencias', details.get('quantity')),
        ]
        amount_labels = {'Precio de venta'}
    elif entity == 'Compras':
        fields = [
            ('ID de compra', details.get('id')),
            ('Proveedor', details.get('supplier_name')),
            ('Producto', details.get('product_name')),
            ('Cantidad', details.get('quantity')),
            ('Total', details.get('total')),
            ('Fecha', details.get('date')),
        ]
        amount_labels = {'Total'}
    else:
        fields = [
            ('ID de gasto', details.get('id')),
            ('Categoría', details.get('category')),
            ('Descripción', details.get('description')),
            ('Monto', details.get('amount')),
            ('Responsable', details.get('responsible')),
            ('Fecha', details.get('date')),
        ]
        amount_labels = {'Monto'}

    return [
        {'label': label, 'value': format_history_amount(value) if label in amount_labels else str(value)}
        for label, value in fields
        if value is not None and value != ''
    ]

# RUTAS - PÁGINA PÚBLICA Y PANEL
@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/dashboard')
def dashboard():
    clients_count = len(read_json_file(CLIENTS_FILE))
    suppliers_count = len(read_json_file(SUPPLIERS_FILE))
    sales_count = len(read_json_file(SALES_FILE))
    buys_count = len(read_json_file(BUYS_FILE))
    stock_items = len(read_json_file(STOCK_FILE))
    invoices_count = len(read_json_file(INVOICES_FILE))
    expenses_count = len(read_json_file(EXPENSES_FILE))
    admin_user = session.get('admin_user', 'Administrador')
    
    return render_template('index.html', 
                         clients=clients_count,
                         suppliers=suppliers_count,
                         sales=sales_count,
                         buys=buys_count,
                         stock=stock_items,
                         invoices=invoices_count,
                         expenses=expenses_count,
                         admin_user=admin_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        destination = 'dashboard' if session.get('role') == 'admin' else 'inventory'
        return redirect(url_for(destination, tab_token=request.args.get('tab_token')))

    error = None
    if request.method == 'POST':
        tab_token = request.form.get('tab_token', '').strip()
        if not 16 <= len(tab_token) <= 128:
            error = 'No se pudo validar esta pestaña. Recarga el formulario e intenta de nuevo.'
            tab_token = secrets.token_urlsafe(32)
    else:
        tab_token = request.args.get('tab_token', '').strip()
        if not 16 <= len(tab_token) <= 128:
            tab_token = secrets.token_urlsafe(32)
    selected_role = request.form.get('role', 'admin')
    if request.method == 'POST' and error is None:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        requested_role = selected_role

        accounts = {
            'admin': (ADMIN_USERNAME, ADMIN_PASSWORD),
            'employee': (EMPLOYEE_USERNAME, EMPLOYEE_PASSWORD),
        }
        account = accounts.get(requested_role)
        if account and username == account[0] and password == account[1]:
            session.clear()
            session.permanent = False
            session['logged_in'] = True
            session['admin_user'] = username
            session['role'] = requested_role
            session['auth_session_id'] = app.config['AUTH_SESSION_ID']
            session['auth_tab_token'] = tab_token
            requested_page = request.args.get('next', '')
            default_page = 'dashboard' if requested_role == 'admin' else 'inventory'
            if requested_role == 'admin' and requested_page.startswith('/') and not requested_page.startswith('//'):
                next_page = requested_page
                separator = '&' if '?' in next_page else '?'
                next_page = f'{next_page}{separator}{urlencode({"tab_token": tab_token})}'
            else:
                next_page = url_for(default_page, tab_token=tab_token)
            return redirect(next_page)
        else:
            error = 'Usuario o contraseña incorrectos. Intenta de nuevo.'

    return render_template('login.html', error=error, tab_token=tab_token, selected_role=selected_role)

@app.route('/history')
def history():
    entries = []
    for entry in reversed(read_json_file(HISTORY_FILE)):
        event = get_history_event(entry)
        if event and entry.get('status', 200) < 400:
            entry['entity'], entry['action'] = event
            entry['display_details'] = format_history_details(entry)
            entries.append(entry)
    return render_template('history.html', entries=entries)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# RUTAS - CLIENTES
@app.route('/clients')
def clients():
    data = read_json_file(CLIENTS_FILE)
    return render_template('clients.html', clients=data)

@app.route('/api/clients', methods=['GET', 'POST'])
def api_clients():
    if request.method == 'POST':
        data = request.get_json()
        data['id'] = get_next_id(CLIENTS_FILE)
        write_json_file(CLIENTS_FILE, data)
        return jsonify({'status': 'success', 'data': data}), 201
    else:
        data = read_json_file(CLIENTS_FILE)
        return jsonify(data)

@app.route('/api/clients/<int:client_id>', methods=['GET', 'DELETE'])
def api_client_detail(client_id):
    if request.method == 'GET':
        data = read_json_file(CLIENTS_FILE)
        for item in data:
            if item.get('id') == client_id:
                return jsonify(item)
        return jsonify({'error': 'Not found'}), 404
    
    elif request.method == 'DELETE':
        data = read_json_file(CLIENTS_FILE)
        updated = [item for item in data if item.get('id') != client_id]
        
        with open(CLIENTS_FILE, 'w', encoding='utf-8') as f:
            for item in updated:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        return jsonify({'status': 'success'})

# RUTAS - PROVEEDORES
@app.route('/suppliers')
def suppliers():
    data = read_json_file(SUPPLIERS_FILE)
    return render_template('suppliers.html', suppliers=data)

@app.route('/api/suppliers', methods=['GET', 'POST'])
def api_suppliers():
    if request.method == 'POST':
        data = request.get_json()
        data['id'] = get_next_id(SUPPLIERS_FILE)
        write_json_file(SUPPLIERS_FILE, data)
        return jsonify({'status': 'success', 'data': data}), 201
    else:
        data = read_json_file(SUPPLIERS_FILE)
        return jsonify(data)

@app.route('/api/suppliers/<int:supplier_id>', methods=['GET', 'DELETE'])
def api_supplier_detail(supplier_id):
    if request.method == 'GET':
        data = read_json_file(SUPPLIERS_FILE)
        for item in data:
            if item.get('id') == supplier_id:
                return jsonify(item)
        return jsonify({'error': 'Not found'}), 404
    
    elif request.method == 'DELETE':
        data = read_json_file(SUPPLIERS_FILE)
        updated = [item for item in data if item.get('id') != supplier_id]
        
        with open(SUPPLIERS_FILE, 'w', encoding='utf-8') as f:
            for item in updated:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        return jsonify({'status': 'success'})

# RUTAS - INVENTARIO
@app.route('/inventory')
def inventory():
    data = read_json_file(STOCK_FILE)
    return render_template('inventory.html', items=data)

@app.route('/api/inventory', methods=['GET', 'POST'])
def api_inventory():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        name = str(data.get('name', '')).strip()
        try:
            quantity = int(data.get('quantity'))
            price = float(data.get('price'))
        except (TypeError, ValueError):
            return jsonify({'error': 'La cantidad y el precio deben ser números válidos'}), 400
        if not name or quantity < 0 or not math.isfinite(price) or price <= 0:
            return jsonify({'error': 'El nombre, una cantidad válida y un precio mayor que cero son obligatorios'}), 400

        data = {'name': name, 'quantity': quantity, 'price': price}
        data['id'] = get_next_id(STOCK_FILE)
        write_json_file(STOCK_FILE, data)
        return jsonify({'status': 'success', 'data': data}), 201
    else:
        data = read_json_file(STOCK_FILE)
        return jsonify(data)

@app.route('/api/inventory/<int:item_id>', methods=['GET', 'DELETE', 'PUT'])
def api_inventory_detail(item_id):
    if request.method == 'GET':
        data = read_json_file(STOCK_FILE)
        for item in data:
            if item.get('id') == item_id:
                return jsonify(item)
        return jsonify({'error': 'Not found'}), 404
    
    elif request.method == 'PUT':
        data = read_json_file(STOCK_FILE)
        update_data = request.get_json(silent=True)
        if not isinstance(update_data, dict):
            return jsonify({'error': 'Los datos enviados no son válidos'}), 400

        item = next((entry for entry in data if entry.get('id') == item_id), None)
        if item is None:
            return jsonify({'error': 'No se encontró el producto'}), 404

        validated_updates = {}
        if 'quantity' in update_data:
            try:
                quantity = int(update_data['quantity'])
            except (TypeError, ValueError):
                return jsonify({'error': 'La cantidad debe ser un número entero'}), 400
            if quantity < 0:
                return jsonify({'error': 'La cantidad no puede ser negativa'}), 400
            validated_updates['quantity'] = quantity

        if 'price' in update_data:
            try:
                price = float(update_data['price'])
            except (TypeError, ValueError):
                return jsonify({'error': 'El precio debe ser un número válido'}), 400
            if not math.isfinite(price) or price <= 0:
                return jsonify({'error': 'El precio debe ser mayor que cero'}), 400
            validated_updates['price'] = price

        if not validated_updates:
            return jsonify({'error': 'Indica un precio o una cantidad para actualizar'}), 400

        item.update(validated_updates)
        with open(STOCK_FILE, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

        return jsonify({'status': 'success', 'data': item})
    
    elif request.method == 'DELETE':
        data = read_json_file(STOCK_FILE)
        deleted_item = next((item for item in data if item.get('id') == item_id), None)
        if deleted_item is None:
            return jsonify({'error': 'No se encontró el producto'}), 404
        updated = [item for item in data if item.get('id') != item_id]
        
        with open(STOCK_FILE, 'w', encoding='utf-8') as f:
            for item in updated:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        return jsonify({'status': 'success', 'data': deleted_item})

# RUTAS - VENTAS
@app.route('/sales')
def sales():
    data = read_json_file(SALES_FILE)
    return render_template('sales.html', sales=data)

@app.route('/api/sales', methods=['GET', 'POST'])
def api_sales():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            product_id = int(data.get('product_id'))
            quantity = int(data.get('quantity'))
        except (TypeError, ValueError):
            return jsonify({'error': 'El ID del producto y la cantidad son obligatorios'}), 400
        if product_id <= 0 or quantity <= 0:
            return jsonify({'error': 'El ID del producto y la cantidad deben ser mayores que cero'}), 400

        inventory = read_json_file(STOCK_FILE)
        product = next((item for item in inventory if item.get('id') == product_id), None)
        if product is None:
            return jsonify({'error': 'No existe un producto con ese ID'}), 404
        if product.get('quantity', 0) < quantity:
            return jsonify({'error': 'Existencias insuficientes'}), 400
        try:
            unit_price = float(product.get('price'))
        except (TypeError, ValueError):
            unit_price = 0
        if not math.isfinite(unit_price) or unit_price <= 0:
            return jsonify({'error': 'El producto no tiene un precio válido en el inventario'}), 400

        data['product_id'] = product_id
        data['product_name'] = product.get('name', '')
        data['quantity'] = quantity
        data['unit_price'] = unit_price
        data['total'] = round(unit_price * quantity, 2)
        data['id'] = get_next_id(SALES_FILE)
        if 'date' not in data:
            data['date'] = datetime.now().strftime('%Y-%m-%d')

        product['quantity'] -= quantity
        
        # Guardar inventario actualizado
        with open(STOCK_FILE, 'w', encoding='utf-8') as f:
            for item in inventory:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        write_json_file(SALES_FILE, data)
        
        # GENERAR FACTURA AUTOMÁTICAMENTE
        invoice = {
            'invoice_id': get_next_id(INVOICES_FILE),
            'sale_id': data['id'],
            'client_id': data.get('client_id'),
            'client_name': data.get('client_name'),
            'product_id': data.get('product_id'),
            'product_name': data.get('product_name'),
            'quantity': data.get('quantity'),
            'unit_price': data.get('unit_price', 0) if data.get('unit_price') else (data.get('total', 0) / data.get('quantity', 1) if data.get('quantity') else 0),
            'subtotal': data.get('total', 0),
            'tax': data.get('total', 0) * 0.00,  # IVA 19%
            'total': data.get('total', 0) * 1.00,
            'date': data['date'],
            'time': datetime.now().strftime('%H:%M:%S'),
            'payment_method': data.get('payment_method', 'Efectivo'),
            'status': 'Pagada'
        }
        write_json_file(INVOICES_FILE, invoice)
        
        return jsonify({'status': 'success', 'data': data, 'invoice': invoice}), 201
    else:
        data = read_json_file(SALES_FILE)
        return jsonify(data)

@app.route('/api/sales/by-date', methods=['POST'])
def api_sales_by_date():
    data = request.get_json()
    date1 = data.get('date1')
    date2 = data.get('date2')
    
    sales = read_json_file(SALES_FILE)
    result = [s for s in sales if date1 <= s.get('date', '') <= date2]
    
    return jsonify(result)

@app.route('/invoices')
def invoices():
    data = read_json_file(INVOICES_FILE)
    return render_template('invoices.html', invoices=data)

@app.route('/api/invoices', methods=['GET'])
def api_invoices():
    data = read_json_file(INVOICES_FILE)
    return jsonify(data)

@app.route('/api/invoices/<int:invoice_id>', methods=['GET', 'DELETE'])
def api_invoice_detail(invoice_id):
    if request.method == 'GET':
        data = read_json_file(INVOICES_FILE)
        for item in data:
            if item.get('invoice_id') == invoice_id:
                return jsonify(item)
        return jsonify({'error': 'Not found'}), 404
    
    elif request.method == 'DELETE':
        data = read_json_file(INVOICES_FILE)
        updated = [item for item in data if item.get('invoice_id') != invoice_id]
        
        with open(INVOICES_FILE, 'w', encoding='utf-8') as f:
            for item in updated:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        return jsonify({'status': 'success'})

# RUTAS -  jsonify(result)

@app.route('/api/sales/<int:sale_id>', methods=['GET', 'DELETE'])
def api_sale_detail(sale_id):
    if request.method == 'GET':
        data = read_json_file(SALES_FILE)
        for item in data:
            if item.get('id') == sale_id:
                return jsonify(item)
        return jsonify({'error': 'Not found'}), 404
    
    elif request.method == 'DELETE':
        data = read_json_file(SALES_FILE)
        deleted_sale = next((item for item in data if item.get('id') == sale_id), None)
        if deleted_sale is None:
            return jsonify({'error': 'No se encontró la venta'}), 404
        updated = [item for item in data if item.get('id') != sale_id]
        
        with open(SALES_FILE, 'w', encoding='utf-8') as f:
            for item in updated:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        return jsonify({'status': 'success', 'data': deleted_sale})

# RUTAS - COMPRAS
@app.route('/purchases')
def purchases():
    data = read_json_file(BUYS_FILE)
    return render_template('purchases.html', purchases=data)

@app.route('/api/purchases', methods=['GET', 'POST'])
def api_purchases():
    if request.method == 'POST':
        data = request.get_json()
        data['id'] = get_next_id(BUYS_FILE)
        if 'date' not in data:
            data['date'] = datetime.now().strftime('%Y-%m-%d')
        
        write_json_file(BUYS_FILE, data)
        return jsonify({'status': 'success', 'data': data}), 201
    else:
        data = read_json_file(BUYS_FILE)
        return jsonify(data)

@app.route('/api/purchases/<int:purchase_id>', methods=['GET', 'DELETE'])
def api_purchase_detail(purchase_id):
    if request.method == 'GET':
        data = read_json_file(BUYS_FILE)
        for item in data:
            if item.get('id') == purchase_id:
                return jsonify(item)
        return jsonify({'error': 'Not found'}), 404
    
    elif request.method == 'DELETE':
        data = read_json_file(BUYS_FILE)
        deleted_purchase = next((item for item in data if item.get('id') == purchase_id), None)
        if deleted_purchase is None:
            return jsonify({'error': 'No se encontró la compra'}), 404
        updated = [item for item in data if item.get('id') != purchase_id]
        
        with open(BUYS_FILE, 'w', encoding='utf-8') as f:
            for item in updated:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        return jsonify({'status': 'success', 'data': deleted_purchase})

# RUTAS - GASTOS
@app.route('/expenses')
def expenses():
    data = read_json_file(EXPENSES_FILE)
    return render_template('expenses.html', expenses=data)

@app.route('/api/expenses', methods=['GET', 'POST'])
def api_expenses():
    if request.method == 'POST':
        data = request.get_json()
        data['id'] = get_next_id(EXPENSES_FILE)
        if 'date' not in data:
            data['date'] = datetime.now().strftime('%Y-%m-%d')
        write_json_file(EXPENSES_FILE, data)
        return jsonify({'status': 'success', 'data': data}), 201
    else:
        data = read_json_file(EXPENSES_FILE)
        return jsonify(data)

@app.route('/api/expenses/<int:expense_id>', methods=['GET', 'DELETE'])
def api_expense_detail(expense_id):
    if request.method == 'GET':
        data = read_json_file(EXPENSES_FILE)
        for item in data:
            if item.get('id') == expense_id:
                return jsonify(item)
        return jsonify({'error': 'Not found'}), 404
    
    elif request.method == 'DELETE':
        data = read_json_file(EXPENSES_FILE)
        deleted_expense = next((item for item in data if item.get('id') == expense_id), None)
        if deleted_expense is None:
            return jsonify({'error': 'No se encontró el gasto'}), 404
        updated = [item for item in data if item.get('id') != expense_id]
        
        with open(EXPENSES_FILE, 'w', encoding='utf-8') as f:
            for item in updated:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        return jsonify({'status': 'success', 'data': deleted_expense})

# RUTAS - REPORTES Y GRÁFICAS
@app.route('/api/dashboard-data')
def api_dashboard_data():
    """Obtiene datos para gráficas del dashboard"""
    sales_data = read_json_file(SALES_FILE)
    expenses_data = read_json_file(EXPENSES_FILE)
    
    # Calcular totales de ventas
    total_sales = sum(float(s.get('total', 0)) for s in sales_data)
    
    # Calcular totales de gastos
    total_expenses = sum(float(e.get('amount', 0)) for e in expenses_data)
    
    # Balance neto
    net_balance = total_sales - total_expenses
    
    # Agrupar ventas por día
    sales_by_day = {}
    for sale in sales_data:
        date = sale.get('date', '')
        amount = float(sale.get('total', 0))
        if date not in sales_by_day:
            sales_by_day[date] = 0
        sales_by_day[date] += amount
    
    # Agrupar gastos por día
    expenses_by_day = {}
    for expense in expenses_data:
        date = expense.get('date', '')
        amount = float(expense.get('amount', 0))
        if date not in expenses_by_day:
            expenses_by_day[date] = 0
        expenses_by_day[date] += amount
    
    # Crear datos de gráfica combinada (ventas - gastos)
    all_dates = sorted(set(list(sales_by_day.keys()) + list(expenses_by_day.keys())))
    chart_data = {
        'dates': all_dates,
        'sales': [sales_by_day.get(date, 0) for date in all_dates],
        'expenses': [expenses_by_day.get(date, 0) for date in all_dates],
        'balance': [sales_by_day.get(date, 0) - expenses_by_day.get(date, 0) for date in all_dates]
    }
    
    return jsonify({
        'total_sales': total_sales,
        'total_expenses': total_expenses,
        'net_balance': net_balance,
        'chart_data': chart_data,
        'sales_count': len(sales_data),
        'expenses_count': len(expenses_data)
    })

if __name__ == '__main__':
    app.run(debug=False, threaded=True, host='0.0.0.0', port=5000)
