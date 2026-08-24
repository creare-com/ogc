# Base image for the development container
ARG BASE_URL=python:3.12-slim
FROM ${BASE_URL}

USER root

# We'll be running as a non-root user in a container and may want root permissions
RUN apt update && apt -y install --no-install-recommends nano ssh sudo && apt clean

# Set up user to match the host OS (https://stackoverflow.com/a/78621662/415551)
ARG HOST_USER
ARG HOST_UID
ARG HOST_GID

RUN addgroup --gid "${HOST_GID}" "${HOST_USER}" \
    && adduser --gecos "" --disabled-password --uid "${HOST_UID}" --gid "${HOST_GID}" "${HOST_USER}" \
    && usermod -aG sudo "${HOST_USER}" \
    && echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# create & activate venv
ENV VIRTUAL_ENV=/app/.venv
RUN /usr/local/bin/python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV LD_LIBRARY_PATH="$VIRTUAL_ENV/lib:$LD_LIBRARY_PATH"
RUN chown -R "${HOST_USER}" /app

ENV HOME /home/${HOST_USER}
ENV TMPDIR=/tmp
WORKDIR /home/${HOST_USER}

USER ${HOST_USER}
ENV PATH "/home/${HOST_USER}/.local/bin:$PATH"
