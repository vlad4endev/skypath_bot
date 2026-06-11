.PHONY: deploy logs migrate seed build dev

deploy:
	docker compose up -d --build

logs:
	docker compose logs -f bot

migrate:
	docker compose --profile migrate run --rm migrate

seed:
	docker compose run --rm bot npm run db:seed

build:
	npm run build

dev:
	npm run dev
