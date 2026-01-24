## Guardrails Setup (Makefile)

This project includes a small Makefile to automate installing and configuring
Guardrails dependencies. The Makefile is intended as a **developer convenience**
and does not replace dependency management defined in `pyproject.toml`.

### Prerequisites
- Python 3.9+
- `pip`
- (Recommended) a virtual environment activated

### Available Make Targets

#### Install Guardrails dependencies
```bash
make guardrails-install
