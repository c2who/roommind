MAKEFLAGS += --no-print-directory

VENV_BIN := .venv/bin
FRONTEND_DIR := frontend

PYTHON := $(VENV_BIN)/python
PYTEST := $(if $(wildcard $(VENV_BIN)/pytest),$(VENV_BIN)/pytest,pytest)
PYTEST_FLAGS := -q -p no:warnings
RUFF := $(if $(wildcard $(VENV_BIN)/ruff),$(VENV_BIN)/ruff,ruff)
COMPONENT := roommind
PYTHON_PATHS := custom_components tests
DEPLOY_TARGET = $(DEPLOY_DEST)/custom_components/$(COMPONENT)
RSYNC_FLAGS := -az --checksum --delete --itemize-changes
RSYNC_EXCLUDES := \
	--exclude="__pycache__/" \
	--exclude="*.pyc" \
	--exclude=".DS_Store"

-include .env

define step
	@printf "\n\033[1m==> %s\033[0m\n" "$(1)"
endef

.PHONY: test test-verbose lint format-check format frontend-build deploy install-dev

test:
	@$(PYTEST) $(PYTEST_FLAGS)

test-verbose:
	@$(PYTEST)

lint:
	@$(RUFF) check $(PYTHON_PATHS)

format-check:
	@$(RUFF) format --check $(PYTHON_PATHS)

format:
	@$(RUFF) format $(PYTHON_PATHS)

frontend-build:
	@cd $(FRONTEND_DIR) && npm run build --silent

deploy:
	$(call step,Deploying $(COMPONENT))
	@test -n "$(DEPLOY_DEST)" || (echo "DEPLOY_DEST is not set"; exit 1)
	@if [ "$(SKIP_TESTS)" = "1" ]; then \
		printf "\n\033[2m==> Tests skipped (SKIP_TESTS=1)\033[0m\n"; \
	else \
		printf "\n\033[1m==> Running tests\033[0m\n"; \
		$(MAKE) test; \
	fi
	$(call step,Ruff lint)
	@$(MAKE) lint
	$(call step,Ruff format check)
	@$(MAKE) format-check
	@if [ "$(SKIP_BUILD)" = "1" ]; then \
		printf "\n\033[2m==> Frontend build skipped (SKIP_BUILD=1)\033[0m\n"; \
	else \
		printf "\n\033[1m==> Building frontend\033[0m\n"; \
		$(MAKE) frontend-build; \
	fi
	$(call step,Syncing custom_components/$(COMPONENT))
	@rsync $(RSYNC_FLAGS) $(RSYNC_EXCLUDES) \
		custom_components/$(COMPONENT)/ $(DEPLOY_TARGET)/
	@printf "\n\033[32mDone.\033[0m\n"

install-dev:
	@$(PYTHON) -m pip install -r requirements-dev.txt
	@cd $(FRONTEND_DIR) && npm ci
