setup:
	pip install -r backend/requirements.txt && cd frontend && npm install
seed:
	cd backend && python -m app.seed --reset
test:
	cd backend && python -m pytest -q
web:
	cd frontend && npm run build
run:
	cd backend && uvicorn app.main:app --port 8000
