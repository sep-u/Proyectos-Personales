# 🚗 Proyecto CarWash

Aplicación web desarrollada con **Django + PostgreSQL (Neon)** para la gestión de reservas de un carwash. Permite a los usuarios registrarse, iniciar sesión y realizar reservas en línea.

---

## 🛠️ Tecnologías utilizadas

* Python 3
* Django
* PostgreSQL (Neon – base de datos en la nube)
* HTML / CSS / Bootstrap
* Git & GitHub

---

## 📋 Requisitos previos

Antes de comenzar, asegúrate de tener instalado:

* Python 3.10 o superior
* Git
* Una cuenta en **Neon** ([https://neon.tech](https://neon.tech))

---

## 🚀 Guía para iniciar el proyecto

### 1️⃣ Clonar el repositorio

```bash
git clone https://github.com/sep-u/Proyectos-Personales.git
cd Proyecto\ CarWash
```

---

### 2️⃣ Crear y activar el entorno virtual

```bash
python -m venv venv
```

**Windows:**

```bash
venv\Scripts\activate
```

**Linux / Mac:**

```bash
source venv/bin/activate
```

---

### 3️⃣ Instalar dependencias

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Configurar variables de entorno

Crea un archivo llamado **.env** en la raíz del proyecto y agrega:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require

EMAIL_HOST_USER=tu_correo@gmail.com
EMAIL_HOST_PASSWORD=tu_password_o_app_password
```

⚠️ **Nota:** El archivo `.env` NO debe subirse a GitHub.

---

### 5️⃣ Ejecutar migraciones

```bash
python manage.py migrate
```

---

### 6️⃣ Crear superusuario (opcional)

```bash
python manage.py createsuperuser
```

---

### 7️⃣ Iniciar el servidor

```bash
python manage.py runserver
```

Luego abre tu navegador en: 👉 [http://127.0.0.1:8000/](http://127.0.0.1:8000/) con Ctrl+click

---

## 📧 Envío de correos

El proyecto utiliza **SMTP de Gmail** para enviar correos de confirmación.

Se recomienda usar una **App Password** de Google y no tu contraseña personal.

---

## 👥 Trabajo colaborativo

Gracias al uso de **PostgreSQL en la nube (Neon)**, varios desarrolladores pueden trabajar en el proyecto sin necesidad de instalar la base de datos localmente.

---

## 📌 Estado del proyecto

🟢 En desarrollo

---

## ✍️ Autor

Christopher Sepúlveda

---

⭐ Si te resulta útil este proyecto, ¡no olvides dejar una estrella!
