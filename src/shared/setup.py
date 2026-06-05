from setuptools import setup, find_packages

setup(
    name="banking-shared",
    version="0.1.0",
    description="Shared library for the four-tier microservice AI banking application",
    author="Banking Platform Team",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0,<3.0",
        "pydantic-settings>=2.0,<3.0",
        "sqlalchemy[asyncio]>=2.0,<3.0",
        "asyncpg>=0.29,<1.0",
        "redis>=5.0,<6.0",
        "aiokafka>=0.10,<1.0",
        "motor>=3.4,<4.0",
        "httpx>=0.27,<1.0",
        "bcrypt>=4.1,<5.0",
        "PyJWT>=2.8,<3.0",
        "structlog>=24.0,<25.0",
        "prometheus-client>=0.20,<1.0",
        "python-json-logger>=2.0,<3.0",
    ],
    python_requires=">=3.11",
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)