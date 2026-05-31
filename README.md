# FaceGuard Local Setup

FaceGuard is a Django app with a template frontend in `Frontend/templates`.

## Run Locally

```bash
cd Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Open:

- Home: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/
- Dashboard: http://127.0.0.1:8000/dashboard/
- Guard view: http://127.0.0.1:8000/guard/
- Enrolment: http://127.0.0.1:8000/enrol/

## Database

Local development uses SQLite by default at `Backend/db.sqlite3`.

To use MySQL instead, add this to `Backend/.env`:

```env
DATABASE_ENGINE=mysql
DATABASE_NAME=faceguard_db
DATABASE_USER=faceguard_user
DATABASE_PASSWORD=password
DATABASE_HOST=localhost
DATABASE_PORT=3306
```

## Optional Redis

The app runs locally without Redis. If you want Redis-backed websockets and Celery, set:

```env
REDIS_URL=redis://127.0.0.1:6379/0
```

## Verify

```bash
cd Backend
source venv/bin/activate
python manage.py check
python -m pytest
```
