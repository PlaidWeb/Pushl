all: setup format mypy pylint flake8

.PHONY: setup
setup:
	poetry install

.PHONY: format
format:
	poetry run isort .
	poetry run autopep8 -r --in-place .

.PHONY: pylint
pylint:
	poetry run pylint pushl

.PHONY: flake8
flake8:
	poetry run flake8

.PHONY: mypy
mypy:
	poetry run mypy -p pushl --ignore-missing-imports

.PHONY: preflight
preflight:
	@echo "Checking commit status..."
	@git status --porcelain | grep -q . \
		&& echo "You have uncommitted changes" 1>&2 \
		&& exit 1 || exit 0
	@echo "Checking branch..."
	@[ "$(shell git rev-parse --abbrev-ref HEAD)" != "main" ] \
		&& echo "Can only build from main" 1>&2 \
		&& exit 1 || exit 0
	@echo "Checking upstream..."
	@git fetch \
		&& [ "$(shell git rev-parse main)" != "$(shell git rev-parse main@{upstream})" ] \
		&& echo "main differs from upstream" 1>&2 \
		&& exit 1 || exit 0

.PHONY: build
build: preflight pylint flake8
	poetry build

.PHONY: clean
clean:
	rm -rf dist .mypy_cache .pytest_cache .coverage
	find . -name __pycache__ -print0 | xargs -0 rm -r

.PHONY: test
test:
	echo "Please implement some tests someday"

.PHONY: upload
upload: clean test build
	poetry publish
