FROM python:3.12-slim
WORKDIR /app
COPY opsguard ./opsguard
RUN useradd -r -u 10001 ops && mkdir -p /app/data && chown ops /app/data
USER ops
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "opsguard.app"]
