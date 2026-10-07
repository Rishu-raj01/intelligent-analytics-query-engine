# 3-Minute Demo Script

## 1. Explain the design in one sentence

"The LLM interprets the business question and writes a grounded analytical plan; DuckDB executes the numbers, and a validator/verifier keeps the result auditable."

## 2. Show a simple query

```bash
python main.py --dataset examples/demo_dataset --query "What percentage of total revenue does each product contribute?"
```

Point out:
- `generated_logic` is executable SQL,
- the result comes from DuckDB,
- confidence has a component breakdown,
- `understood_as` and assumptions expose interpretation.

## 3. Show a complex query

```bash
python main.py --dataset examples/demo_dataset --query "Top 2 customers by revenue within each region"
```

Point out the window function / partitioning inside the generated SQL.

## 4. Show feedback learning

Open `examples/demo_dataset/feedback_log.csv` and explain that relevant prior corrections are retrieved instead of blindly inserting the entire log.

## 5. Show engineering quality

```bash
pytest -q
python benchmark.py --dataset dataset
```

Mention exact expected-result tests, CI, Docker and the API endpoint.

## Key tradeoff to say out loud

"I deliberately did not generate arbitrary Python or let the model calculate answers. SQL is easier to validate and audit, while the LLM is used only where it adds value: semantic interpretation and repair."
