# Project Functionality and Requirements

## Project Goal
Build a system that runs selected Small Language Models (SLMs) with configurable hardware limits (RAM and CPU), executes benchmark runs, and records results for each run scenario.

## Core Functional Requirements

### FR-1: Run a model with selected RAM and CPU
- The user can select:
  - model name/version;
  - RAM amount (GB);
  - CPU amount (number of cores).
- The system must run the model using the selected RAM and CPU constraints.
- The system must start a separate benchmark/test execution for that configuration.
- The system must save execution status and results for this run.

### FR-2: Run all selected RAM/CPU combinations separately
- The user can choose multiple RAM values and multiple CPU values.
- The system must generate all RAM x CPU combinations.
- Each combination must be executed as a separate run (independent scenario).
- Each run must have its own status and result record.
- Failure of one combination must not stop processing of other combinations (unless user explicitly cancels).

### FR-3: Handle insufficient resources
- Before or during run startup, the system must validate that required resources are available.
- If resources are insufficient for a given model/configuration, the run must:
  - not be executed as a normal benchmark run;
  - be marked with status: `not_enough_resources`;
  - be saved to results/logs with the selected model, RAM, CPU, timestamp, and reason.
- The system must continue processing other combinations when possible.

## Run Status Requirements
Each run should contain one of the following statuses:
- `pending`
- `running`
- `completed`
- `failed`
- `not_enough_resources`
- `cancelled`

## Data Recording Requirements
For each run, the system should store at least:
- run identifier;
- model name/version;
- selected RAM and CPU;
- selected technology/platform (if applicable);
- start and finish timestamps;
- final status;
- error/failure reason (including insufficient resources details);
- benchmark metrics/results when available.

## User Interface Requirements
- UI must allow model selection.
- UI must allow single RAM/CPU selection for one run.
- UI must allow multi-selection of RAM and CPU for combination runs.
- UI must show progress and status per combination.
- UI must clearly show `not_enough_resources` entries.

## Backend/API Requirements
- API must accept:
  - single run request (one RAM/CPU pair);
  - batch/combinational run request (multiple RAM and CPU values).
- API must return per-run statuses and progress updates.
- API must persist all run outcomes, including insufficient resource cases.

## Validation Rules
- RAM and CPU values must be positive and within allowed limits.
- Duplicate identical run requests may be prevented or marked as repeated.
- Resource availability checks must be performed consistently for every run combination.

## Acceptance Criteria
1. When one model, one RAM value, and one CPU value are selected, exactly one run is executed and saved.
2. When multiple RAM and CPU values are selected, all combinations are executed separately and saved independently.
3. If a combination cannot run due to insufficient resources, that combination is saved with `not_enough_resources` status and does not block valid combinations.
4. Run history contains complete statuses and parameters for all attempts.

