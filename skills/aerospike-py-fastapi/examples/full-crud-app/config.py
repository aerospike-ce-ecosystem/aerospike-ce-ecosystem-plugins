"""
Application settings loaded from environment variables.

Environment variables (all prefixed with APP_):
    APP_AEROSPIKE_HOST            -- Aerospike host (default: 127.0.0.1)
    APP_AEROSPIKE_PORT            -- Aerospike port (default: 3000)
    APP_AEROSPIKE_NAMESPACE       -- Default namespace (default: test)
    APP_AEROSPIKE_SET             -- Default set name (default: demo)
    APP_MAX_CONCURRENT_OPERATIONS -- Backpressure limit (default: 64)
    APP_OTEL_ENDPOINT             -- OTLP gRPC endpoint (default: http://localhost:4317)
    APP_OTEL_SERVICE_NAME         -- OTel service name (default: aerospike-fastapi)
    APP_LOG_LEVEL                 -- aerospike-py log level 0-4 (default: 2 = INFO)
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Aerospike connection
    aerospike_host: str = "127.0.0.1"
    aerospike_port: int = 3000
    aerospike_namespace: str = "test"
    aerospike_set: str = "demo"

    # Backpressure
    max_concurrent_operations: int = 64

    # Observability
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "aerospike-fastapi"
    log_level: int = 2  # LOG_LEVEL_INFO

    model_config = {"env_prefix": "APP_"}


settings = Settings()
