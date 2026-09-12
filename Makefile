.PHONY: test reset validate

test:
	python harness/validate_openapi.py openapi.yaml
	python harness/reset_db.py .
	python -m pytest tests -v

validate:
	python harness/validate_openapi.py openapi.yaml

reset:
	python harness/reset_db.py .