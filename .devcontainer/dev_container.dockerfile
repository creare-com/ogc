# Base image for the development container
ARG BASE_URL=python:3.12-slim
FROM ${BASE_URL}

USER root

# We'll be running as a non-root user in a container and may want root permissions
RUN apt update && apt -y install nano ssh sudo && apt clean

# Install setup tools and dependencies
WORKDIR /app
COPY . /app
RUN pip install --upgrade pip setuptools && pip install .[dev] 

# Set up user to match the host OS (https://stackoverflow.com/a/78621662/415551)
ARG HOST_USER
ARG HOST_UID
ARG HOST_GID

RUN addgroup --gid ${HOST_GID} ${HOST_USER} \
    && adduser --gecos "" --disabled-password --uid ${HOST_UID} --gid ${HOST_GID} ${HOST_USER} \
    && usermod -aG sudo ${HOST_USER} \
    && echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

ENV HOME /home/${HOST_USER}
ENV TMPDIR=/tmp
WORKDIR /home/${HOST_USER}

USER ${HOST_USER}
