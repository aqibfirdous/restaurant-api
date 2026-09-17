.PHONY: test test-mcp run-mcp reset validate

test:
	python harness/validate_openapi.py openapi.yaml
	python harness/reset_db.py .
	python -m pytest tests -v

test-mcp:
	python harness/validate_openapi.py openapi.yaml
	python harness/reset_db.py .
	python -m pytest tests -q
	python -m pytest mcp_gateway/tests -q

run-mcp: reset
	python src/app.py &
	python -m mcp_gateway.server

validate:
	python harness/validate_openapi.py openapi.yaml

reset:
	python harness/reset_db.py .