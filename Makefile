ENGINE ?= docker
COMPOSE_FILE = infra/compose.yml
ENV_FILE = infra/.env

.PHONY: up down logs ps init

init:
	cp -n infra/.env.example infra/.env || true

up:
	$(ENGINE) compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE) up -d

down:
	$(ENGINE) compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE) down

logs:
	$(ENGINE) compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE) logs -f

ps:
	$(ENGINE) compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE) ps