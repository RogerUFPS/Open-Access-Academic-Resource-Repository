# Open Access Academic Resource Repository

## Project

This project aims to make academic resources easier to discover. It provides a platform to organize and explore databases, journals, and other research sources, with intelligent guidance to help researchers find resources relevant to their needs.

## Architecture

### Frontend

A Next.js application that provides the user interface and connects researchers with the catalog and its discovery features.

### Backend

A Django REST API that manages the catalog, research resources, and harvesting operations.

### Worker

A Celery worker that processes resource harvesting tasks outside the API request cycle.

### Message broker

RabbitMQ delivers tasks from the API to the worker. Its data is kept in a persistent Docker volume.

### Scheduler

A single Celery Beat service schedules HTTP dispatch tasks in UTC. The tasks use
the existing RabbitMQ broker and Celery worker to call the backend endpoints;
the backend then queues long-running harvest and link-check work. Configure
`SCHEDULER_API_TOKEN` and `SCHEDULER_SERVICE_USER_ID` as deployment secrets and
point the service user to a non-superadmin account with the `check_link`
permission. Do not run multiple Beat instances. Link-check endpoints return an
existing unfinished run for duplicate/idempotent requests, and a database
constraint prevents overlapping runs of the same mode.

## Design decisions

The frontend and backend run as separate services so each can evolve and scale independently. Harvesting runs asynchronously through Celery and RabbitMQ to keep long running work from delaying user requests. The scheduler calls the backend API instead of duplicating its business logic. The database is configured through environment variables and can run outside the Docker Compose stack, allowing the application and database to be managed independently.
