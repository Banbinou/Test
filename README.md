 Process Mining App (FastAPI + React)

Application de process mining avec backend **FastAPI + PM4Py** et frontend **React**.

## Fonctionnalités

- Import de fichiers `.csv`, `.xlsx` ou `.xls`
- Aperçu automatique des 20 premières lignes
- Mapping dynamique des colonnes vers les champs PM4Py
  - Case ID
  - Activity
  - Timestamp
  - Resource (optionnel)
- Lancement d'analyses:
  - Process discovery (DFG + start/end activities)
  - Statistiques globales (nombre de cas, activités, durées)
  - Variants (top 20)

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API:

- `POST /upload` : charge un fichier et renvoie colonnes + preview + file_id
- `POST /analyze` : exécute les analyses selon mapping + file_id
- `GET /health` : healthcheck

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Par défaut le frontend appelle `http://localhost:8000`.
Vous pouvez surcharger via:

```bash
VITE_API_URL=http://localhost:8000 npm run dev
```
