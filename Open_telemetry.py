from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Setup for various common frameworks - implement what's needed for your stack
def configure_telemetry(service_name, environment):
    """Configure OpenTelemetry with appropriate service name and environment."""
    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": environment,  # on-prem, aws, azure, gcp, etc.
    })
    
    # Set the global trace provider
    trace_provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="otel-collector:4317"))
    trace_provider.add_span_processor(processor)
    trace.set_tracer_provider(trace_provider)
    
    # Auto-instrument common frameworks
    RequestsInstrumentor().instrument()
    
    return trace_provider

# Example usage in a Flask application
def instrument_flask_app(app, service_name, environment):
    configure_telemetry(service_name, environment)
    FlaskInstrumentor().instrument_app(app, tracer_provider=trace.get_tracer_provider())

# Example usage in a FastAPI application
def instrument_fastapi_app(app, service_name, environment):
    configure_telemetry(service_name, environment)
    FastAPIInstrumentor().instrument_app(app)

# Custom decorator to instrument any function
def trace_function(func):
    tracer = trace.get_tracer(__name__)
    
    def wrapper(*args, **kwargs):
        with tracer.start_as_current_span(func.__name__):
            return func(*args, **kwargs)
    
    return wrapper

# Example for manual instrumentation of critical code sections
def manual_instrumentation_example():
    tracer = trace.get_tracer(__name__)
    
    with tracer.start_as_current_span("critical-operation") as span:
        # Add attributes to provide context
        span.set_attribute("operation.importance", "high")
        span.set_attribute("operation.category", "database")
        
        # Your critical code here
        result = perform_operation()
        
        # Record the outcome
        span.set_attribute("operation.outcome", "success" if result else "failure")
        
        return result