SHELL := /bin/bash

# Auto-detect Python: prefers a repo-local .venv (Windows or Linux layout),
# then falls back to the Windows Python inside WSL, then python3 on native
# Linux/macOS. Override any time: make PYTHON=/path/to/python test
_VENV_PY := $(firstword $(wildcard .venv/Scripts/python.exe) $(wildcard .venv/bin/python))
# Find the first Windows Python (sorted ascending) that has pytest installed
_WIN_PY := $(shell for p in $$(ls /mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/python.exe 2>/dev/null | sort -V); do $$p -c "import pytest" 2>/dev/null && echo $$p && break; done)
PYTHON ?= $(if $(_VENV_PY),$(_VENV_PY),$(if $(_WIN_PY),$(_WIN_PY),python3))

.PHONY: run run-sim run-admin-dashboard seed-demo-data screenshots intake-sheet test test-hotspot lint

# Run the app on the kiosk (requires hardware + CUPS + pigpiod)
# Runs from repo root so config.py finds .env here (SSP/.env is gitignored)
# -X utf8 forces UTF-8 stdout on Windows (avoids CP1252 emoji errors)
# Over SSH there is no DISPLAY: show the GUI on the kiosk's own screen if its
# X session is up (logs stay in the SSH terminal), else run headless so the
# app still starts with no screen attached.
run:
	@if [ -z "$$DISPLAY" ] && [ -z "$$WAYLAND_DISPLAY" ]; then \
		if [ -S /tmp/.X11-unix/X0 ]; then \
			echo "No display in this shell: showing the app on the kiosk screen (DISPLAY=:0)"; \
			export DISPLAY=:0; \
		else \
			echo "No display found: running headless (QT_QPA_PLATFORM=offscreen)"; \
			export QT_QPA_PLATFORM=offscreen; \
		fi; \
	fi; \
	$(PYTHON) -X utf8 SSP/main_app.py

# Run the app in simulation mode — no GPIO, CUPS, or modem required
run-sim:
	SIM_MODE=true $(PYTHON) -X utf8 SSP/main_app.py

# Render every screen to screenshots/<screen>.png as the 1920x1080 kiosk shows it
# (headless, simulated hardware, temp DB). The reference picture for UI changes.
screenshots:
	$(PYTHON) -X utf8 scripts/render_screens.py --out screenshots

# Write intake_sheet.pdf, the Wi-Fi/email how-to sheet taped to the kiosk, from
# this kiosk's .env. Add ARGS=--print to send it to the printer too.
intake-sheet:
	$(PYTHON) -X utf8 scripts/make_intake_sheet.py $(ARGS)

# Run the Admin Dashboard — a separate FastAPI/Uvicorn process from the
# kiosk GUI and the Wi-Fi portal (see
# docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md).
# Never started by main_app.py. Runs from the repo root so config.py finds
# .env here, same as run/run-sim; PYTHONPATH=SSP makes the admin_dashboard
# package importable without a real Uvicorn socket needing --app-dir.
run-admin-dashboard:
	PYTHONPATH=SSP $(PYTHON) -X utf8 -m admin_dashboard.main

# Seed the SIM_MODE-gated demo fixture DB (SSP/database/ssp_database.sim.db)
# so /accounting has realistic data to show before the kiosk has
# accumulated any real transactions. Refuses to run unless SIM_MODE=true.
# Never touches the real ssp_database.db.
seed-demo-data:
	SIM_MODE=true PYTHONPATH=SSP $(PYTHON) -X utf8 -m admin_dashboard.seed_demo_data

# Run the test suite
test:
	$(PYTHON) -m pytest tests/ -v

# Check the hotspot's generated firewall + dnsmasq config against the real
# tools in a Linux container (needs Docker). See tests/hotspot_container/.
test-hotspot:
	bash tests/hotspot_container/run.sh

# Lint the source tree (max line length 120, ignoring cache dirs)
lint:
	$(PYTHON) -m flake8 SSP/ scripts/
