# Architecture Technique — KYJA BEAUTÉ

## Vue d'ensemble

Application de gestion de salon de coiffure multi-phases (MVP → V1 → V2), avec moteur de réservation à ressources multiples, module RH pour coiffeuses indépendantes, finance, logistique de livraison, inventaire hybride et programme de fidélité.

---

## Stack Technique

| Couche | Technologie | Rôle |
|---|---|---|
| **Frontend** | Next.js 14 (React 18) + TailwindCSS | Interface web responsive, SSR, PWA |
| **Backend** | FastAPI (Python 3.12) | API REST, logique métier, calculs |
| **Base de données** | PostgreSQL | Données transactionnelles et relationnelles |
| **ORM** | SQLAlchemy 2.0 + Alembic | Accès BDD, migrations |
| **Cache / Broker** | Redis | Disponibilités, sessions, rate limiting, broker Celery |
| **Tâches async** | Celery + Celery Beat | Rappels RDV, envois email, traitement images |
| **Stockage fichiers** | Cloudflare R2 + CDN | Images galerie, preuves de livraison, portfolios |
| **Auth** | JWT + bcrypt + refresh tokens | Authentification sécurisée |
| **Email** | Resend | Confirmations RDV, statuts livraison |
| **Push notifications** | Web Push API (PWA) | Alertes temps-réel clientes |
| **Hébergement** | VPS (Hostinger ou OVH) | Backend + BDD + Redis + Celery |
| **Déploiement frontend** | Vercel | Hébergement Next.js |

---

## Infrastructure

### Hébergement VPS

```
VPS (Hostinger / OVH)
├── FastAPI          → Uvicorn + Gunicorn (port 8000)
├── Celery Worker    → Tâches asynchrones (rappels, emails, traitement images)
├── Celery Beat      → Planificateur cron (rappels J-1 et H-2)
├── PostgreSQL       → Option managée du fournisseur VPS
├── Redis            → Cache + Broker Celery + sessions
└── Nginx            → Reverse proxy + SSL/TLS (Certbot/Let's Encrypt)
```

> **Note PIPEDA :** Choisir un VPS avec datacenter au Canada si possible (OVH Beauharnois QC, ou Hostinger région US-Est la plus proche). Documenter la localisation des données dans la politique de confidentialité.

> **RAM minimale recommandée :** 2 GB pour faire tourner FastAPI + Celery + Redis + PostgreSQL simultanément.

### Backups PostgreSQL

```
Backups automatisés
├── pg_dump quotidien via cron système
├── Rétention : 30 jours
├── Stockage : bucket R2 séparé (kyja-backups)
└── Test de restauration : trimestriel (procédure documentée)
```

### Stockage des fichiers (Cloudflare R2)

```
Upload (FastAPI) → R2 Bucket (kyja-beaute)
                        ├── /gallery/              → Photos coiffures & produits (publiques)
                        ├── /products/             → Images catalogue (publiques)
                        ├── /deliveries/           → Preuves de livraison (accès admin)
                        ├── /portfolios/pending/   → Upload initial coiffeuse (privé)
                        └── /portfolios/approved/  → Validé par admin, visible aux clientes

Accès client → CDN Cloudflare → cache géographique → image servie en < 100ms
```

**Cycle de vie du portfolio coiffeuse :**
```
Coiffeuse uploade → /portfolios/pending/ (privé)
       ↓ Validation admin
/portfolios/approved/ → visible aux clientes pour choisir leur coiffeuse
```

**Pipeline d'upload (asynchrone) :**
```
1. Client envoie fichier → FastAPI
2. FastAPI valide (type MIME, taille max) → retourne 202 Accepted
3. Fichier stocké temporairement sur disque VPS
4. Tâche Celery : Pillow optimise l'image
5. Tâche Celery : upload vers R2 via boto3
6. URL sauvegardée en base
```

---

## Architecture Applicative

### Vue globale des couches

```
┌─────────────────────────────────────────┐
│         Next.js (React 18)              │
│         TailwindCSS + shadcn/ui         │  ← Frontend (Vercel)
│         PWA (notifications push web)    │
└──────────────────┬──────────────────────┘
                   │ HTTPS / REST API
┌──────────────────▼──────────────────────┐
│              FastAPI                    │
│         Pydantic (validation)           │  ← Backend (VPS)
│         SQLAlchemy ORM                  │
│         JWT Auth Middleware             │
└──────┬──────────────┬───────────────────┘
       │              │
┌──────▼──────┐  ┌────▼─────────────────────┐
│ PostgreSQL  │  │  Redis                   │
│ (données    │  │  ├── Cache disponibilités │
│  métier)    │  │  ├── Sessions            │
└─────────────┘  │  ├── Rate limiting       │
                 │  └── Broker Celery       │
                 └────────────┬─────────────┘
                              │
                 ┌────────────▼─────────────┐
                 │  Celery Worker + Beat    │
                 │  (rappels, emails,       │
                 │   traitement images)     │
                 └──────────────────────────┘
```

### Modules Backend (FastAPI)

```
api/
├── auth/           → Inscription, login, refresh token, logout, révocation
├── clients/        → Profil, historique, droit à l'oubli (PIPEDA)
├── bookings/       → Moteur de réservation, détection conflits ressources
├── services/       → Catalogue prestations + durées
├── hairdressers/   → Profils, disponibilités, coefficients, portfolio
├── resources/      → Bacs de lavage, casques (équipements partagés)
├── products/       → Catalogue produits, images, prix
├── inventory/      → Stocks, alertes POS, synchronisation
├── orders/         → Commandes, livraisons, preuves photo
├── finance/        → Commissions, loyers de chaise, réconciliation
├── loyalty/        → Points, récompenses, historique
├── notifications/  → Email (Resend) + Push (Web Push)
├── tasks/          → Tâches Celery (rappels RDV, envois email, resize images)
└── admin/          → Validation portfolio, validation paiements, POS
```

---

## Base de Données — Schéma Principal

### Entités et relations clés

```
clients
  ├── appointments (1→N)
  ├── orders (1→N)
  ├── loyalty_account (1→1)
  └── consent_records (1→N)           ← PIPEDA

appointments
  ├── hairdresser (N→1)
  ├── service (N→1)
  ├── resources (N→N via appointment_resources)   ← détection conflits
  └── financial_record (1→1)

hairdressers
  ├── availability_slots (1→N)
  ├── portfolio_files (1→N)           ← pending ou approved
  ├── experience_level (coefficient)
  └── payment_records (1→N)

products
  ├── inventory (1→1)
  ├── images (1→N)
  └── order_items (1→N)

orders
  ├── order_items (1→N)
  ├── delivery_record (1→1)
  └── delivery_photos (1→N)          ← preuves de livraison R2

resources                             ← bacs de lavage, casques, etc.
  └── appointments (N→N via appointment_resources)

refresh_tokens                        ← gestion des sessions
  ├── user_id (→ clients ou hairdressers)
  ├── token_hash
  ├── expires_at
  └── revoked_at
```

### Droit à l'oubli — Anonymisation (pas suppression)

Le droit à l'oubli PIPEDA est implémenté par **anonymisation** afin de préserver l'intégrité des données financières et comptables.

```
Données anonymisées :
  ├── clients.nom          → "CLIENT_SUPPRIMÉ"
  ├── clients.email        → "anon_{id}@supprimé.kyja"
  ├── clients.telephone    → NULL
  └── clients.adresse      → NULL

Données conservées (intégrité légale / comptable) :
  ├── appointments         → conservés avec référence anonymisée
  ├── financial_records    → conservés et anonymisés (7 ans, fiscal)
  └── consent_records      → conservés intégralement (obligation légale)

Données supprimées :
  ├── Photos de profil
  ├── Préférences
  └── Adresses de livraison
```

> `ON DELETE CASCADE` uniquement sur les données sans valeur légale ou comptable (photos de profil, préférences, adresses de livraison).

### Règles d'intégrité importantes

- Transactions ACID pour toute création de rendez-vous (vérification atomique coiffeuse + équipement).
- `consent_records` : jamais supprimé ni anonymisé (preuve légale de consentement).
- `financial_records` : jamais supprimé, anonymisé lors du droit à l'oubli.

---

## Moteur de Réservation

### Logique de calcul de durée

```
Durée totale = (Durée de base du service × Coefficient coiffeuse) + Buffer Time

Coefficients :
  - Junior  : 1.3  (30% de temps supplémentaire)
  - Senior  : 1.0  (durée standard)
  - Expert  : 0.85 (15% plus rapide)
```

### Détection de conflits (transaction atomique)

```sql
BEGIN;
  SET statement_timeout = '5s';       -- éviter les deadlocks prolongés

  -- 1. Vérifier disponibilité coiffeuse
  SELECT ... FOR UPDATE;

  -- 2. Vérifier disponibilité équipements requis
  SELECT ... FOR UPDATE;

  -- 3. Si tout disponible : créer le rendez-vous
  INSERT INTO appointments ...;
  INSERT INTO appointment_resources ...;
COMMIT;
```

> Tous les calculs et validations sont effectués **avant** le `BEGIN` pour garder la transaction aussi courte que possible.

### Cache Redis des disponibilités

- TTL de 60 secondes pour les disponibilités affichées côté client.
- **Invalidation proactive** à chaque création ou annulation de rendez-vous (ne pas attendre l'expiration du TTL).
- La vérification finale reste toujours en base (source de vérité).

---

## Authentification & Autorisation

### Flux d'authentification

```
Login → FastAPI vérifie bcrypt → JWT Access Token (15 min) + Refresh Token (30 jours, HttpOnly cookie)
      → Refresh token stocké hashé dans la table refresh_tokens

Rotation des tokens :
  /auth/refresh → invalide l'ancien refresh token + génère un nouveau pair access + refresh

Révocation :
  Changement de mot de passe → tous les refresh_tokens de l'utilisateur révoqués
  Déconnexion globale        → idem
```

### Rôles

| Rôle | Accès |
|---|---|
| `client` | Profil, réservations, commandes, fidélité |
| `hairdresser` | Propre agenda, propre finance, propre portfolio |
| `admin` | Tout + validation portfolios, réconciliation, POS, inventaire |

### Sécurité

- Mots de passe : hachage **bcrypt** (cost factor 12)
- Rate limiting sur `/auth/login` : 5 tentatives / 15 min par IP (via Redis)
- HTTPS obligatoire (Certbot + Let's Encrypt sur Nginx)
- Headers de sécurité : `CSP`, `X-Frame-Options`, `HSTS` configurés dans Nginx
- Protection CSRF uniquement sur `/auth/refresh` (double-submit cookie). Les autres endpoints sont protégés par le Bearer token JWT.
- Données sensibles chiffrées au repos : numéros de téléphone, adresses (PostgreSQL `pgcrypto`)

---

## Notifications

Tous les envois sont traités de manière **asynchrone via Celery**. En cas d'échec, retry automatique avec backoff exponentiel (3 tentatives maximum).

### Email — Resend

- Confirmation de réservation
- Rappel de rendez-vous (J-1 et H-2) — planifié par Celery Beat
- Statuts de commande et livraison
- Bienvenue à l'inscription

### Push — Web Push API (PWA)

- Statuts de livraison en temps-réel ("En route", "Livré")
- Rappels de rendez-vous
- Offres promotionnelles (opt-in explicite requis — PIPEDA)

> Lors du passage à React Native (Phase 3+), les notifications push migrent vers **Expo Push Notifications** sans changement côté backend.

---

## Stratégie Mobile

### Phase 1-2 : PWA (Progressive Web App)

Next.js configuré avec `next-pwa` :
- Installable sur iOS et Android depuis le navigateur
- Fonctionne sans connexion (pages de base en cache)
- Notifications push via **Web Push API**
- Zéro coût de développement supplémentaire

### Phase 3+ : Application Native (React Native + Expo)

- Partage la logique d'appel API avec le web (hooks/services)
- Même backend FastAPI, aucun changement nécessaire
- Publication sur App Store et Google Play
- Notifications push via Expo Push Notifications

---

## Conformité PIPEDA (Canada)

| Exigence | Implémentation |
|---|---|
| Consentement marketing explicite | Opt-in checkbox à l'inscription, loggué dans `consent_records` |
| Droit à l'oubli | Anonymisation des données personnelles (voir schéma BDD) |
| Accès aux données personnelles | Endpoint `GET /clients/me/export` → JSON de toutes les données |
| Chiffrement en transit | HTTPS obligatoire (Let's Encrypt) |
| Chiffrement au repos | `pgcrypto` pour données PII sensibles (téléphone, adresse) |
| Audit trail financier | `financial_records` anonymisés, jamais supprimés |
| Plan de réponse aux brèches | Procédure documentée : détection → notification CPVP sous 72h → notification clientes affectées |
| Localisation des données | VPS avec datacenter au Canada (OVH Beauharnois QC recommandé) — documenté dans politique de confidentialité |

### Politique de rétention des données

| Type de donnée | Durée de rétention |
|---|---|
| Données clients actifs | Durée de la relation + 2 ans |
| `financial_records` | 7 ans (obligations fiscales canadiennes) |
| Preuves de livraison (photos) | 7 ans |
| Logs d'audit | 7 ans |
| Données clients inactifs anonymisées | Purge automatique via tâche Celery mensuelle |

---

## Observabilité

### Logging

- `structlog` (Python) : logs JSON structurés sur tous les endpoints critiques
- Niveaux : `INFO` pour les opérations normales, `ERROR` pour les exceptions, `WARNING` pour les tentatives suspectes (auth, rate limit)

### Monitoring

- Health check : `GET /health` → vérifie PostgreSQL + Redis
- Uptime monitoring : UptimeRobot (gratuit) → alerte email/SMS si indisponible

### Alertes critiques

- Taux d'erreur 5xx > 1% → alerte immédiate
- Espace disque VPS < 20% → alerte
- Backup échoué → alerte

---

## Stratégie de Tests

| Type | Outil | Cible |
|---|---|---|
| Unitaires | pytest | Calcul durées, commissions, coefficients, conflits |
| Intégration | pytest + PostgreSQL test | Transactions atomiques du moteur de réservation |
| End-to-end | Playwright | Réservation, droit à l'oubli, POS |
| Contrat API | schemathesis | Validation spec OpenAPI générée par FastAPI |

---

## Feuille de Route Technique

### MVP (Phase 1)
- [ ] Projet Next.js + FastAPI initialisés
- [ ] Schéma PostgreSQL complet + migrations Alembic
- [ ] Auth (inscription / login / JWT / refresh tokens / révocation)
- [ ] Catalogue services et produits
- [ ] Moteur de réservation (conflits coiffeuse + équipement)
- [ ] Profil client + historique
- [ ] Interface admin de base
- [ ] Celery + Celery Beat configurés
- [ ] Notifications email (Resend) via Celery
- [ ] Backups automatisés PostgreSQL → R2
- [ ] Health check + UptimeRobot
- [ ] Déploiement VPS + Nginx + SSL
- [ ] PWA activée

### V1 (Phase 2)
- [ ] Module RH coiffeuses (portail + portfolio privé + validation admin)
- [ ] Module finance (commissions + loyers + réconciliation)
- [ ] Livraison maison (zonage + preuves photo async)
- [ ] Inventaire hybride (online + POS sync)
- [ ] Notifications push Web Push API

### V2 (Phase 3)
- [ ] Coefficients d'expérience coiffeuses (Junior/Senior/Expert)
- [ ] Programme de fidélité (points automatiques)
- [ ] POS rapide ("Vente Comptoir" + popup inventaire 10s)
- [ ] React Native (Expo) + Expo Push Notifications

---

## Points à Définir

| Point | Statut |
|---|---|
| Nom de domaine (`kyjabeaute.ca` ?) | À confirmer |
| Région exacte du VPS (pour documentation PIPEDA) | À confirmer lors de l'achat |
| Intégration paiement en ligne (Phase 2+) | Non décidé — Stripe ou PayPal Canada |
| Langue(s) de l'interface (FR seulement, ou FR + EN ?) | À confirmer |
