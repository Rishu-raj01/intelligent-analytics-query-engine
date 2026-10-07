# Architecture Notes

## Components

### DatasetLoader
Loads all CSVs except `feedback_log.csv`, reads the data dictionary and NL query file, profiles each table, samples values and infers candidate shared columns between tables.

### LLMPlanner
Converts the business question into a strict `QueryPlan`. The plan includes SQL plus an auditable description of intent, schema usage, assumptions, complexity and expected output.

### FeedbackStore
Retrieves semantically relevant prior feedback. Embedding retrieval is optional and automatically falls back to lexical similarity.

### SQL validator
Creates a fail-closed execution boundary. It allows read-only analytical SQL, blocks dangerous commands/external readers and rejects unknown relations.

### DuckDBExecutor
Registers DataFrames as in-memory relations and executes the query. All final numbers come from the database.

### Verifier
Performs lightweight deterministic post-execution checks, such as expected aliases and basic consistency between declared analytical features and the returned shape.

### Confidence
Combines independent evidence rather than using the LLM's self-reported confidence alone.

## Error path

```text
plan -> validate -> execute
           |          |
           +---error--+
                |
                v
          grounded repair
                |
                v
        validate + execute again
```

The repair prompt receives the concrete failure message and the previous plan. Repair is bounded by `MAX_REPAIR_ATTEMPTS`.

## Prompt-injection boundary

The model prompt explicitly treats the following as data, not instructions:

- user query,
- data dictionary,
- schema samples,
- feedback text.

Even if the model is manipulated, the local validator prevents file readers, DDL/DML and unknown tables from reaching execution.

## Scaling path

For a larger production deployment:

1. Persist datasets in a managed analytical store instead of DataFrames.
2. Replace in-memory feedback embeddings with a vector store.
3. Add AST-based SQL lineage/type checks.
4. Cache query plans by normalized question and dataset fingerprint.
5. Add execution quotas/timeouts.
6. Route low-confidence plans to a critic/human review path.
