.PHONY: deploy logs migrate doctor build dev

deploy:
	./scripts/deploy.sh

logs:
	./scripts/logs.sh bot

migrate:
	docker compose exec -T bot alembic upgrade head

doctor:
	./scripts/doctor.sh

build:
	docker compose build bot

dev:
	python -m bot.main
