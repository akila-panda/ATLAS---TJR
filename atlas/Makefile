.PHONY: dev stop logs clean restart-engine restart-api status 
 
dev: 
	docker-compose up --build 
 
stop: 
	docker-compose down 
 
logs: 
	docker-compose logs -f 
 
restart-engine: 
	docker-compose restart signal-engine 
 
restart-api: 
	docker-compose restart api-server 
 
clean: 
	docker-compose down -v 
 
status: 
	docker-compose ps 
