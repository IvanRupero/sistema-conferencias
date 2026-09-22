import os 
from datetime import datetime
import io
import re
import zipfile
from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///conferencias.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'clave_secura_teschi_2026'

# Configuración de Correo Electrónico (Flask-Mail)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'tu_correo@gmail.com'          # Cambia por tu correo de Gmail
app.config['MAIL_PASSWORD'] = 'tu_contrasena_de_aplicacion' # Contraseña de aplicación de Gmail
app.config['MAIL_DEFAULT_SENDER'] = 'tu_correo@gmail.com'

db = SQLAlchemy(app)
mail = Mail(app)

class Conferencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    ponente = db.Column(db.String(100), nullable=False)
    fecha = db.Column(db.String(50), nullable=False)
    horas = db.Column(db.Integer, nullable=False)
    form_url = db.Column(db.String(300), nullable=True)
    asistencias = db.relationship('Asistencia', backref='conferencia', lazy=True, cascade='all, delete-orphan')

class Asistencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    grupo = db.Column(db.String(20), nullable=False)
    correo = db.Column(db.String(120), nullable=False)  # Correo electrónico obligatorio
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Control de acceso con lector QR (Entrada y Salida)
    hora_entrada = db.Column(db.DateTime, nullable=True)
    hora_salida = db.Column(db.DateTime, nullable=True)
    constancia_enviada = db.Column(db.Boolean, default=False)
    
    conferencia_id = db.Column(db.Integer, db.ForeignKey('conferencia.id'), nullable=False)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    conferencias = Conferencia.query.all()
    return render_template('index.html', conferencias=conferencias)

@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        ponente = request.form.get('ponente')
        fecha = request.form.get('fecha')
        horas = request.form.get('horas')
        form_url = request.form.get('form_url')
        
        if titulo and ponente and fecha and horas:
            nueva_conf = Conferencia(titulo=titulo, ponente=ponente, fecha=fecha, horas=int(horas), form_url=form_url)
            db.session.add(nueva_conf)
            db.session.commit()
            flash('Conferencia creada exitosamente.', 'success')
        return redirect(url_for('admin_dashboard'))
    
    conferencias = Conferencia.query.all()
    return render_template('admin_dashboard.html', conferencias=conferencias)

@app.route('/registro/<int:conferencia_id>', methods=['GET', 'POST'])
def registrar_asistencia(conferencia_id):
    conferencia = Conferencia.query.get_or_404(conferencia_id)
    if request.method == 'POST':
        matricula = request.form.get('matricula').strip()
        nombre = request.form.get('nombre')
        grupo = request.form.get('grupo')
        correo = request.form.get('correo').strip()
        
        existente = Asistencia.query.filter_by(matricula=matricula, conferencia_id=conferencia_id).first()
        if existente:
            flash('Esta matrícula ya cuenta con registro de asistencia para esta conferencia.', 'warning')
        else:
            nueva_asistencia = Asistencia(
                matricula=matricula, 
                nombre=nombre, 
                grupo=grupo, 
                correo=correo, 
                conferencia_id=conferencia_id
            )
            db.session.add(nueva_asistencia)
            db.session.commit()
            return redirect(url_for('registro_exitoso', asistencia_id=nueva_asistencia.id))
            
    return render_template('registrar.html', conferencia=conferencia)

@app.route('/registro-exitoso/<int:asistencia_id>')
def registro_exitoso(asistencia_id):
    asistencia = Asistencia.query.get_or_404(asistencia_id)
    return render_template('exito.html', asistencia=asistencia)

# Ruta que procesa el escaneo del QR (Entrada / Salida automática)
@app.route('/escanear-qr/<int:asistencia_id>', methods=['GET'])
def escanear_qr(asistencia_id):
    asistencia = Asistencia.query.get_or_404(asistencia_id)
    ahora = datetime.now()
    
    mensaje = ""
    tipo_alerta = "success"
    
    if not asistencia.hora_entrada:
        asistencia.hora_entrada = ahora
        db.session.commit()
        mensaje = f"¡Entrada registrada correctamente para {asistencia.nombre} a las {ahora.strftime('%H:%M:%S')}!"
    elif not asistencia.hora_salida:
        asistencia.hora_salida = ahora
        db.session.commit()
        mensaje = f"¡Salida registrada correctamente para {asistencia.nombre} a las {ahora.strftime('%H:%M:%S')}! Constancia enviada por correo."
        
        # Envía la constancia por correo al completar entrada y salida
        enviar_constancia_por_correo(asistencia)
    else:
        mensaje = f"El alumno {asistencia.nombre} ya completó su registro de entrada y salida previamente."
        tipo_alerta = "warning"
        
    return render_template('resultado_escaneo.html', mensaje=mensaje, tipo_alerta=tipo_alerta, asistencia=asistencia)

def enviar_constancia_por_correo(asistencia):
    if asistencia.constancia_enviada:
        return
        
    conferencia = asistencia.conferencia
    
    # Generar PDF en memoria
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    p.setStrokeColorRGB(0.1, 0.5, 0.2)
    p.setLineWidth(4)
    p.rect(30, 30, width - 60, height - 60)
    
    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width / 2.0, height - 90, "TECNOLÓGICO DE ESTUDIOS SUPERIORES DE CHIMALHUACÁN")
    p.setFont("Helvetica", 11)
    p.drawCentredString(width / 2.0, height - 110, "División de Administración")
    
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width / 2.0, height - 170, "CONSTANCIA DE ASISTENCIA")
    
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2.0, height - 220, "Se otorga la presente constancia a:")
    
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2.0, height - 260, asistencia.nombre.upper())
    
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2.0, height - 310, f"Por su valiosa participación en la conferencia '{conferencia.titulo}',")
    p.drawCentredString(width / 2.0, height - 340, f"impartida por {conferencia.ponente}, con valor de {conferencia.horas} horas.")
    p.drawCentredString(width / 2.0, height - 370, f"Celebrada el {conferencia.fecha}.")
    
    p.setFont("Helvetica", 10)
    p.drawString(60, 120, f"Folio de Registro: TESCHI-ADM-{asistencia.id:04d}")
    p.drawString(60, 100, f"Matrícula: {asistencia.matricula} | Grupo: {asistencia.grupo}")
    
    p.line(width - 250, 140, width - 60, 140)
    p.drawCentredString(width - 155, 120, "Jefatura de la División de Administración")
    
    p.showPage()
    p.save()
    buffer.seek(0)
    
    try:
        msg = Message(
            subject=f"Constancia de Asistencia - {conferencia.titulo}",
            recipients=[asistencia.correo],
            body=f"Hola {asistencia.nombre},\n\nAdjunto encontrarás tu constancia de acreditación por tu asistencia a la conferencia '{conferencia.titulo}'.\n\n¡Felicidades!\nAtentamente,\nDivisión de Administración - TESCHI"
        )
        msg.attach(f"Constancia_{asistencia.matricula}.pdf", "application/pdf", buffer.read())
        mail.send(msg)
        
        asistencia.constancia_enviada = True
        db.session.commit()
    except Exception as e:
        print(f"Error al enviar correo: {e}")

@app.route('/constancia/<int:asistencia_id>')
def generar_constancia(asistencia_id):
    asistencia = Asistencia.query.get_or_404(asistencia_id)
    conferencia = asistencia.conferencia
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    p.setStrokeColorRGB(0.1, 0.5, 0.2)
    p.setLineWidth(4)
    p.rect(30, 30, width - 60, height - 60)
    
    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width / 2.0, height - 90, "TECNOLÓGICO DE ESTUDIOS SUPERIORES DE CHIMALHUACÁN")
    p.setFont("Helvetica", 11)
    p.drawCentredString(width / 2.0, height - 110, "División de Administración")
    
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width / 2.0, height - 170, "CONSTANCIA DE ASISTENCIA")
    
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2.0, height - 220, "Se otorga la presente constancia a:")
    
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2.0, height - 260, asistencia.nombre.upper())
    
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2.0, height - 310, f"Por su valiosa participación en la conferencia '{conferencia.titulo}',")
    p.drawCentredString(width / 2.0, height - 340, f"impartida por {conferencia.ponente}, con valor de {conferencia.horas} horas.")
    p.drawCentredString(width / 2.0, height - 370, f"Celebrada el {conferencia.fecha}.")
    
    p.setFont("Helvetica", 10)
    p.drawString(60, 120, f"Folio de Registro: TESCHI-ADM-{asistencia.id:04d}")
    p.drawString(60, 100, f"Matrícula: {asistencia.matricula} | Grupo: {asistencia.grupo}")
    
    p.line(width - 250, 140, width - 60, 140)
    p.drawCentredString(width - 155, 120, "Jefatura de la División de Administración")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"Constancia_{asistencia.matricula}.pdf", mimetype='application/pdf')

@app.route('/constancias-zip/<int:conferencia_id>')
def descargar_zip_constancias(conferencia_id):
    conferencia = Conferencia.query.get_or_404(conferencia_id)
    if not conferencia.asistencias:
        flash('No hay asistencias registradas para esta conferencia.', 'warning')
        return redirect(url_for('admin_dashboard'))
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for asistencia in conferencia.asistencias:
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            width, height = letter
            
            p.setStrokeColorRGB(0.1, 0.5, 0.2)
            p.setLineWidth(4)
            p.rect(30, 30, width - 60, height - 60)
            
            p.setFont("Helvetica-Bold", 14)
            p.drawCentredString(width / 2.0, height - 90, "TECNOLÓGICO DE ESTUDIOS SUPERIORES DE CHIMALHUACÁN")
            p.setFont("Helvetica", 11)
            p.drawCentredString(width / 2.0, height - 110, "División de Administración")
            
            p.setFont("Helvetica-Bold", 18)
            p.drawCentredString(width / 2.0, height - 170, "CONSTANCIA DE ASISTENCIA")
            
            p.setFont("Helvetica", 12)
            p.drawCentredString(width / 2.0, height - 220, "Se otorga la presente constancia a:")
            
            p.setFont("Helvetica-Bold", 16)
            p.drawCentredString(width / 2.0, height - 260, asistencia.nombre.upper())
            
            p.setFont("Helvetica", 12)
            p.drawCentredString(width / 2.0, height - 310, f"Por su valiosa participación en la conferencia '{conferencia.titulo}',")
            p.drawCentredString(width / 2.0, height - 340, f"impartida por {conferencia.ponente}, con valor de {conferencia.horas} horas.")
            p.drawCentredString(width / 2.0, height - 370, f"Celebrada el {conferencia.fecha}.")
            
            p.setFont("Helvetica", 10)
            p.drawString(60, 120, f"Folio de Registro: TESCHI-ADM-{asistencia.id:04d}")
            p.drawString(60, 100, f"Matrícula: {asistencia.matricula} | Grupo: {asistencia.grupo}")
            
            p.line(width - 250, 140, width - 60, 140)
            p.drawCentredString(width - 155, 120, "Jefatura de la División de Administración")
            
            p.showPage()
            p.save()
            
            buffer.seek(0)
            nombre_limpio = re.sub(r'[^a-zA-Z0-9]', '_', asistencia.nombre)
            filename = f"Constancia_{asistencia.matricula}_{nombre_limpio}.pdf"
            zf.writestr(filename, buffer.getvalue())
            
    memory_file.seek(0)
    nombre_conf_limpio = re.sub(r'[^a-zA-Z0-9]', '_', conferencia.titulo)
    return send_file(memory_file, as_attachment=True, download_name=f"Constancias_{nombre_conf_limpio}.zip", mimetype='application/zip')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
