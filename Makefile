install:
	python -m pip install -r requirements.txt

test:
	pytest -q

run-all:
	python main.py --dataset dataset --all --output results.json

api:
	uvicorn api:app --reload

benchmark:
	python benchmark.py --dataset dataset --output benchmark_results.json
