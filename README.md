# KYJA BEAUTÉ

Application digitale pour le salon de coiffure **KYJA BEAUTÉ** (Québec) : catalogue de prestations/produits, réservation en ligne, profil client conforme LPRPDE, gestion des coiffeuses.

Cahier des charges complet : [`PRD.md`](PRD.md). Architecture technique détaillée : [`ARCHITECTURE.md`](ARCHITECTURE.md).

## État actuel

Le **backend** (FastAPI) est en développement actif. Modules fonctionnels à ce jour :

- **Auth** — inscription/connexion client, JWT + refresh token hybride (Bearer en mémoire + cookie HttpOnly), CSRF sur `/auth/refresh`, rate limiting du login.
- **Catalogue** — CRUD services/produits (admin), médias (images) uploadés en fichiers réels, traités (EXIF strippé, WebP, pHash).
- **Coiffeuses** — création/gestion par un admin, liste publique des coiffeuses actives.
- **Réservation** — réservation catalogue (prix/durée connus) et "sur devis" (description et/ou photos, suggestion de prix/durée par similarité d'image), détection de conflit verrouillée en base, confirmation de devis par un admin.
- **Vue admin** — liste de tous les rendez-vous, filtrable par statut/coiffeuse/date.

Le **frontend** (Next.js) n'est pas encore démarré — seul le scaffold existe dans `frontend/`.

Sécurité déjà en place dans le code (bcrypt, chiffrement au repos, ORM paramétré, 404-not-403, etc.) ; l'outillage de sécurité automatisé (scan de dépendances, lint sécurité, headers HTTP, CI) est volontairement différé à une étape ultérieure.

## Stack technique

Voir [`ARCHITECTURE.md`](ARCHITECTURE.md) pour le détail complet. En résumé : FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL + Redis, JWT/bcrypt, stockage local de dev (Cloudflare R2 prévu en production). Frontend prévu : Next.js + TailwindCSS.

## Démarrer le backend en local

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # puis renseigner les valeurs (DB, SECRET_KEY, ENCRYPTION_KEY...)
alembic upgrade head
uvicorn app.main:app --reload
```

Documentation interactive de l'API : `http://localhost:8000/docs` (en environnement `development`).

### Créer le premier compte admin

Aucun endpoint HTTP ne crée de compte admin (pour éviter toute escalade de privilèges) :

```bash
python scripts/create_admin.py --email admin@example.com --password "..."
```

### Tests

```bash
cd backend
pytest
```

La suite tourne contre une base Postgres de test dédiée et une base Redis logique isolée (voir `tests/conftest.py`) — jamais contre les données de développement.

## Structure du dépôt

```
PRD.md              → Cahier des charges fonctionnel
ARCHITECTURE.md      → Architecture technique détaillée
backend/             → API FastAPI (voir ci-dessus)
frontend/            → Scaffold Next.js (à construire)
```
