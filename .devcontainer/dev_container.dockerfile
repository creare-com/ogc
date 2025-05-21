# Base image for the development container
FROM python:3.11-slim

# Setup working directory
WORKDIR /app
COPY . /app

# Install setup tools and dependencies
RUN pip install --upgrade pip setuptools && pip install .[dev] 