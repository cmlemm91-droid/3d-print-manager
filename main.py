from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import sqlite3
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")

DB_PATH = "print_manager.db"
CAD_RATE = 45.00

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, material TEXT, color TEXT, weight REAL, price_per_kg REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY, name TEXT, street TEXT, house_number TEXT, zip TEXT, city TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS printers (id INTEGER PRIMARY KEY, name TEXT, cost_per_hour REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY, customer_id INTEGER, status TEXT, FOREIGN KEY(customer_id) REFERENCES customers(id))")
        # EXPLICIT COLUMN DEFINITION FOR CAD_HOURS
        conn.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, invoice_id INTEGER, model TEXT, material_id INTEGER, printer_id INTEGER, weight_used REAL, duration_hours REAL, cad_hours REAL, price REAL, status TEXT, FOREIGN KEY(invoice_id) REFERENCES invoices(id), FOREIGN KEY(material_id) REFERENCES inventory(id), FOREIGN KEY(printer_id) REFERENCES printers(id))")
        res = conn.execute("SELECT count(*) FROM printers").fetchone()
        if res[0] == 0:
            conn.execute("INSERT INTO printers (name, cost_per_hour) VALUES (?, ?)", ("Standard", 1.50))

init_db()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    db = get_db()
    q = "SELECT orders.*, customers.name as customer_name FROM orders JOIN invoices ON orders.invoice_id = invoices.id JOIN customers ON invoices.customer_id = customers.id WHERE orders.status = 'Wartend'"
    open_orders = db.execute(q).fetchall()
    low_stock = db.execute("SELECT * FROM inventory WHERE weight < 500").fetchall()
    return templates.TemplateResponse(request=request, name="index.html", context={"open_orders": open_orders, "low_stock": low_stock})

@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, show_done: bool = False):
    db = get_db()
    q1 = "SELECT orders.*, customers.name as customer_name FROM orders JOIN invoices ON orders.invoice_id = invoices.id JOIN customers ON invoices.customer_id = customers.id WHERE orders.status = 'Wartend'"
    open_orders = db.execute(q1).fetchall()
    done_orders = []
    if show_done:
        q2 = "SELECT orders.*, customers.name as customer_name FROM orders JOIN invoices ON orders.invoice_id = invoices.id JOIN customers ON invoices.customer_id = customers.id WHERE orders.status = 'Fertig'"
        done_orders = db.execute(q2).fetchall()
    customers = db.execute("SELECT * FROM customers").fetchall()
    inventory = db.execute("SELECT * FROM inventory").fetchall()
    printers = db.execute("SELECT * FROM printers").fetchall()
    return templates.TemplateResponse(request=request, name="orders.html", context={"open_orders": open_orders, "done_orders": done_orders, "customers": customers, "inventory": inventory, "printers": printers, "show_done": show_done})

@app.post("/add_order")
async def add_order(
    customer_id: int = Form(...),
    model: str = Form(...),
    material_id: int = Form(...),
    printer_id: int = Form(...),
    weight_used: float = Form(...),
    duration_hours: float = Form(...),
    cad_hours: float = Form(0.0)
):
    db = get_db()

    # 1. Preise laden
    mat = db.execute("SELECT price_per_kg FROM inventory WHERE id = ?", (material_id,)).fetchone()
    pri = db.execute("SELECT cost_per_hour FROM printers WHERE id = ?", (printer_id,)).fetchone()

    if not mat or not pri:
        raise HTTPException(status_code=404, detail="Material oder Drucker nicht gefunden")

    # 2. Rechnung zuordnen
    inv_check = db.execute("SELECT id FROM invoices WHERE customer_id = ? AND status = 'Offen'", (customer_id,)).fetchone()
    if inv_check:
        invoice_id = inv_check['id']
    else:
        db.execute("INSERT INTO invoices (customer_id, status) VALUES (?, ?)", (customer_id, "Offen"))
        invoice_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 3. Preis berechnen
    m_cost = (weight_used / 1000) * mat['price_per_kg']
    t_cost = duration_hours * pri['cost_per_hour']
    c_cost = cad_hours * CAD_RATE
    total = round(m_cost + t_cost + c_cost + 2.00, 2)

    # 4. In Datenbank speichern
    # Wir benennen die Spalten explizit, um Fehler zu vermeiden
    sql = """INSERT INTO orders
             (invoice_id, model, material_id, printer_id, weight_used, duration_hours, cad_hours, price, status)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    params = (invoice_id, model, material_id, printer_id, weight_used, duration_hours, cad_hours, total, "Wartend")

    db.execute("UPDATE inventory SET weight = weight - ? WHERE id = ?", (weight_used, material_id))
    db.execute(sql, params)
    db.commit()

    return RedirectResponse(url="/orders", status_code=303)

@app.get("/complete/{order_id}")
async def complete_order(order_id: int):
    db = get_db()
    db.execute("UPDATE orders SET status = 'Fertig' WHERE id = ?", (order_id,))
    order = db.execute("SELECT invoice_id FROM orders WHERE id = ?", (order_id,)).fetchone()
    inv_id = order['invoice_id']
    rem = db.execute("SELECT count(*) as count FROM orders WHERE invoice_id = ? AND status = 'Wartend'", (inv_id,)).fetchone()
    if rem['count'] == 0:
        db.execute("UPDATE invoices SET status = 'Fertig' WHERE id = ?", (inv_id,))
    db.commit()
    return RedirectResponse(url="/orders", status_code=303)

@app.get("/reopen/{order_id}")
async def reopen_order(order_id: int):
    db = get_db()
    db.execute("UPDATE orders SET status = 'Wartend' WHERE id = ?", (order_id,))
    order = db.execute("SELECT invoice_id FROM orders WHERE id = ?", (order_id,)).fetchone()
    db.execute("UPDATE invoices SET status = 'Offen' WHERE id = ?", (order['invoice_id'],))
    db.commit()
    return RedirectResponse(url="/orders", status_code=303)

@app.get("/edit/{order_id}", response_class=HTMLResponse)
async def edit_order(request: Request, order_id: int):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order: raise HTTPException(status_code=404, detail="Not found")
    inventory = db.execute("SELECT * FROM inventory").fetchall()
    printers = db.execute("SELECT * FROM printers").fetchall()
    return templates.TemplateResponse(request=request, name="edit_order.html", context={"order": order, "inventory": inventory, "printers": printers})

@app.post("/update_order/{order_id}")
async def update_order(order_id: int, model: str = Form(...), material_id: int = Form(...), printer_id: int = Form(...), weight_used: float = Form(...), duration_hours: float = Form(...), cad_hours: float = Form(0.0)):
    db = get_db()
    old = db.execute("SELECT weight_used, material_id FROM orders WHERE id = ?", (order_id,)).fetchone()
    mat = db.execute("SELECT price_per_kg FROM inventory WHERE id = ?", (material_id,)).fetchone()
    pri = db.execute("SELECT cost_per_hour FROM printers WHERE id = ?", (printer_id,)).fetchone()
    total = round(((weight_used / 1000) * mat['price_per_kg']) + (duration_hours * pri['cost_per_hour']) + (cad_hours * CAD_RATE) + 2.00, 2)
    diff = weight_used - old['weight_used']
    if material_id == old['material_id']:
        db.execute("UPDATE inventory SET weight = weight - ? WHERE id = ?", (diff, material_id))
    else:
        db.execute("UPDATE inventory SET weight = weight + ? WHERE id = ?", (old['weight_used'], old['material_id']))
        db.execute("UPDATE inventory SET weight = weight - ? WHERE id = ?", (weight_used, material_id))
    db.execute("UPDATE orders SET model=?, material_id=?, printer_id=?, weight_used=?, duration_hours=?, cad_hours=?, price=? WHERE id=?", (model, material_id, printer_id, weight_used, duration_hours, cad_hours, total, order_id))
    db.commit()
    return RedirectResponse(url="/orders", status_code=303)

@app.get("/delete/{order_id}")
async def delete_order(order_id: int):
    db = get_db()
    order = db.execute("SELECT weight_used, material_id FROM orders WHERE id = ?", (order_id,)).fetchone()
    db.execute("UPDATE inventory SET weight = weight + ? WHERE id = ?", (order['weight_used'], order['material_id']))
    db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    db.commit()
    return RedirectResponse(url="/orders", status_code=303)

@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request):
    db = get_db()
    inv = db.execute("SELECT * FROM inventory").fetchall()
    return templates.TemplateResponse(request=request, name="inventory.html", context={"inventory": inv})

@app.post("/add_material")
async def add_material(material: str = Form(...), color: str = Form(...), weight: float = Form(...), price_per_kg: float = Form(...)):
    db = get_db()
    db.execute("INSERT INTO inventory (material, color, weight, price_per_kg) VALUES (?, ?, ?, ?)", (material, color, weight, price_per_kg))
    db.commit()
    return RedirectResponse(url="/inventory", status_code=303)

@app.post("/add_stock")
async def add_stock(material_id: int = Form(...), amount: float = Form(...)):
    db = get_db()
    db.execute("UPDATE inventory SET weight = weight + ? WHERE id = ?", (amount, material_id))
    db.commit()
    return RedirectResponse(url="/inventory", status_code=303)

@app.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    db = get_db()
    cust = db.execute("SELECT * FROM customers").fetchall()
    return templates.TemplateResponse(request=request, name="customers.html", context={"customers": cust})

@app.post("/add_customer")
async def add_customer(name: str = Form(...), street: str = Form(...), house_number: str = Form(...), zip: str = Form(...), city: str = Form(...)):
    db = get_db()
    db.execute("INSERT INTO customers (name, street, house_number, zip, city) VALUES (?, ?, ?, ?, ?)", (name, street, house_number, zip, city))
    db.commit()
    return RedirectResponse(url="/customers", status_code=303)

@app.get("/customer/{customer_id}", response_class=HTMLResponse)
async def customer_detail(request: Request, customer_id: int):
    db = get_db()
    cust = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not cust: raise HTTPException(status_code=404, detail="Not found")
    invs = db.execute("SELECT * FROM invoices WHERE customer_id = ?", (customer_id,)).fetchall()
    data = []
    for i in invs:
        ords = db.execute("SELECT * FROM orders WHERE invoice_id = ?", (i['id'],)).fetchall()
        data.append({"invoice": i, "orders": ords})
    return templates.TemplateResponse(request=request, name="customer_detail.html", context={"customer": cust, "invoices": data})

@app.get("/printers", response_class=HTMLResponse)
async def printers_page(request: Request):
    db = get_db()
    pris = db.execute("SELECT * FROM printers").fetchall()
    return templates.TemplateResponse(request=request, name="printers.html", context={"printers": pris})

@app.post("/add_printer")
async def add_printer(name: str = Form(...), cost_per_hour: float = Form(...)):
    db = get_db()
    db.execute("INSERT INTO printers (name, cost_per_hour) VALUES (?, ?)", (name, cost_per_hour))
    db.commit()
    return RedirectResponse(url="/printers", status_code=303)

@app.get("/invoice/{invoice_id}")
async def create_invoice(invoice_id: int):
    db = get_db()
    q_inv = "SELECT invoices.id, customers.name, customers.street, customers.house_number, customers.zip, customers.city FROM invoices JOIN customers ON invoices.customer_id = customers.id WHERE invoices.id = ?"
    inv = db.execute(q_inv, (invoice_id,)).fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")

    items = db.execute("SELECT * FROM orders WHERE invoice_id = ?", (invoice_id,)).fetchall()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 20)
    pdf.set_text_color(0, 0, 255)
    pdf.cell(0, 10, "3D PRINT SERVICE", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Ihr Name / Firma", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, "Ihre Strasse 123, 12345 Ihre Stadt", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, "Email: info@ihre-domain.de | Tel: 0123-456789", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)
    pdf.line(0, pdf.get_y(), 210, pdf.get_y())
    pdf.ln(10)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(100, 10, "Rechnung an:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(0, 10, f"Rechnungsnummer: {inv['id']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 7, f"{inv['name']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, f"{inv['street']} {inv['house_number']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, f"{inv['zip']} {inv['city']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(15)

    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(100, 10, " Position", border=1, fill=True)
    pdf.cell(40, 10, "Menge/Zeit", border=1, fill=True, align='C')
    pdf.cell(50, 10, "Preis", border=1, fill=True, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", size=11)
    total_sum = 0

    for item in items:
        db_h = get_db()
        mat = db_h.execute("SELECT price_per_kg FROM inventory WHERE id = ?", (item['material_id'],)).fetchone()
        pri = db_h.execute("SELECT cost_per_hour FROM printers WHERE id = ?", (item['printer_id'],)).fetchone()

        p_kg = float(mat['price_per_kg']) if mat else 0.0
        c_hr = float(pri['cost_per_hour']) if pri else 0.0

        # EXPLICIT CONVERSION TO FLOAT
        try:
            c_hours = float(item['cad_hours'])
        except (TypeError, ValueError):
            c_hours = 0.0

        m_cost = (float(item['weight_used']) / 1000) * p_kg
        t_cost = float(item['duration_hours']) * c_hr
        c_cost = c_hours * CAD_RATE
        f_fee = 2.00

        pdf.set_font("Helvetica", 'B', 11)
        pdf.cell(0, 10, f" Modell: {item['model']}", border='TR', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", size=11)

        pdf.cell(100, 8, "  Materialkosten", border='L', align='L')
        pdf.cell(40, 8, f"{item['weight_used']}g", border=1, align='C')
        pdf.cell(50, 8, f"{m_cost:.2f} EUR", border=1, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.cell(100, 8, "  Maschinenzeit", border='L', align='L')
        pdf.cell(40, 8, f"{item['duration_hours']}h", border=1, align='C')
        pdf.cell(50, 8, f"{t_cost:.2f} EUR", border=1, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if c_hours > 0:
            pdf.cell(100, 8, "  CAD-Designzeit", border='L', align='L')
            pdf.cell(40, 8, f"{c_hours}h", border=1, align='C')
            pdf.cell(50, 8, f"{c_cost:.2f} EUR", border=1, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.cell(100, 8, "  Bearbeitungsgebühr", border='L', align='L')
        pdf.cell(40, 8, "1 Stk", border=1, align='C')
        pdf.cell(50, 8, f"{f_fee:.2f} EUR", border=1, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.line(pdf.get_x(), pdf.get_y(), 210, pdf.get_y())
        total_sum += (m_cost + t_cost + c_cost + f_fee)

    pdf.ln(10)
    pdf.set_font("Helvetica", 'B', 14)
    pdf.cell(140, 10, "Gesamtsumme:", align='R')
    pdf.cell(50, 10, f"{total_sum:.2f} EUR", border=1, align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(20)
    pdf.set_font("Helvetica", 'I', 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 10, "Vielen Dank für Ihren Auftrag!", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, "Bitte überweisen Sie den Betrag innerhalb von 14 Tagen.", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    file_path = f"invoice_{invoice_id}.pdf"
    pdf.output(file_path)
    return FileResponse(file_path, filename=f"Rechnung_{inv['name']}.pdf")

@app.get("/invoice_from_order/{order_id}")
async def invoice_from_order(order_id: int):
    db = get_db()
    inv_id = db.execute("SELECT invoice_id FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not inv_id: return RedirectResponse(url="/")
    return RedirectResponse(url=f"/invoice/{inv_id['invoice_id']}", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
