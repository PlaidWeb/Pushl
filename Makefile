all: format mypy pylint flake8

.PHONY: format
format:
	pipenv run isort -y
	pipenv run autopep8 -r --in-place .

.PHONY: pylint
pylint:
	pipenv run pylint pushl

.PHONY: flake8
flake8:
	pipenv run flake8

.PHONY: mypy
mypy:
	pipenv run mypy -p pushl --ignore-missing-imports

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
	pipenv run python3 setup.py sdist
	pipenv run python3 setup.py bdist_wheel

.PHONY: clean
clean:
	rm -rf build dist .mypy_cache

.PHONY: upload
upload: clean build
	pipenv run twine upload dist/*
